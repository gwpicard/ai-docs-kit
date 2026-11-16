"""Measure PDF vector marks and infer format-specific unit grids."""

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Literal

import pdfplumber
from pydantic import BaseModel

from ai_docs_kit.brand.intake import Role
from ai_docs_kit.brand.pages import PageEntry, PageIndex, load_pages
from ai_docs_kit.facts.pdf import to_hex
from ai_docs_kit.model.source import Format

VECTORS = Path("theme/ingest/vectors.json")
Kind = Literal["rule", "stroke", "fill"]
Shape = Literal["line", "rect", "curve"]
Orientation = Literal["horizontal", "vertical"]


class VectorMark(BaseModel):
    kind: Kind
    shape: Shape
    x0: float
    y0: float
    x1: float
    y1: float
    colour: str | None = None
    width: float | None = None
    width_assumed: bool = False
    orientation: Orientation | None = None
    background: bool = False


class PageVectors(BaseModel):
    file: str
    page: int
    role: Role
    format: Format
    width: float
    height: float
    marks: list[VectorMark]


class UnitGrid(BaseModel):
    format: Format
    width: float
    height: float
    pages: int
    roles: list[Role]
    columns: int | None
    rows: int | None
    unit_w: float | None
    unit_h: float | None
    x_score: float
    y_score: float


class Tally(BaseModel):
    kind: Kind
    colour: str | None
    width: float | None
    orientation: Orientation | None
    count: int
    area_share: float | None


class FormatVectors(BaseModel):
    format: Format
    grid: UnitGrid | None
    tallies: list[Tally]


class VectorReport(BaseModel):
    schema_version: int = 1
    pages: list[PageVectors]
    formats: list[FormatVectors]


def _marks(raw: dict[str, Any], shape: Shape, area: float) -> list[VectorMark]:
    x0, y0, x1, y1 = (float(raw[key]) for key in ("x0", "top", "x1", "bottom"))
    w, h = abs(x1 - x0), abs(y1 - y0)
    marks: list[VectorMark] = []
    if shape != "line" and raw.get("fill"):
        thin = shape == "rect" and min(w, h) <= 3 and max(w, h) >= 10 * min(w, h)
        marks.append(
            VectorMark(
                shape=shape,
                x0=x0,
                y0=y0,
                x1=x1,
                y1=y1,
                kind="rule" if thin else "fill",
                colour=to_hex(raw.get("non_stroking_color")),
                width=min(w, h) if thin else None,
                orientation=("horizontal" if w >= h else "vertical") if thin else None,
                background=not thin and w * h >= 0.95 * area,
            )
        )
    if raw.get("stroke"):
        width = float(raw.get("linewidth") or 0)
        orientation: Orientation | None = None
        if shape == "line":
            if h < 0.5:
                orientation = "horizontal"
            elif w < 0.5:
                orientation = "vertical"
        marks.append(
            VectorMark(
                shape=shape,
                x0=x0,
                y0=y0,
                x1=x1,
                y1=y1,
                kind="rule" if orientation else "stroke",
                colour=to_hex(raw.get("stroking_color")),
                width=width or 1.0,
                width_assumed=width == 0,
                orientation=orientation,
            )
        )
    return marks


def _page(entry: PageEntry, page: Any) -> PageVectors:
    objects: tuple[tuple[Shape, Any], ...] = (("line", page.lines), ("rect", page.rects), ("curve", page.curves))
    marks = [
        mark for shape, items in objects for raw in items for mark in _marks(raw, shape, entry.width * entry.height)
    ]
    return PageVectors(
        file=entry.file,
        page=entry.page,
        role=entry.role,
        format=entry.format,
        width=entry.width,
        height=entry.height,
        marks=marks,
    )


def _edges(page: PageVectors, index: PageIndex) -> tuple[set[float], set[float]]:
    xs: set[float] = set()
    ys: set[float] = set()
    for mark in page.marks:
        if mark.background:
            continue
        xs.add(round(mark.x0, 2))
        ys.add(round(mark.y0, 2))
        if not (mark.kind == "rule" and mark.shape == "rect" and mark.orientation == "vertical"):
            xs.add(round(mark.x1, 2))
        if not (mark.kind == "rule" and mark.shape == "rect" and mark.orientation == "horizontal"):
            ys.add(round(mark.y1, 2))
    for entry in index.pages:
        if (entry.file, entry.page) == (page.file, page.page):
            for image in entry.images:
                xs.update((round(image.box.x0, 2), round(image.box.x1, 2)))
                ys.update((round(image.box.y0, 2), round(image.box.y1, 2)))
    return ({x for x in xs if 0.75 < x < page.width - 0.75}, {y for y in ys if 0.75 < y < page.height - 0.75})


def _axis(edges: list[float], length: float) -> tuple[int | None, float | None, float]:
    if len(edges) >= 4:
        for n in range(2, 49):
            unit = length / n
            score = sum(abs(edge - round(edge / unit) * unit) <= 0.75 for edge in edges) / len(edges)
            if score >= 0.9:
                return n, unit, score
    return None, None, 0.0


def unit_grid(pages: list[PageVectors], index: PageIndex, format: Format) -> UnitGrid | None:
    candidates = sorted((p for p in pages if p.format == format), key=lambda p: (p.file, p.page))
    preferred = [p for p in candidates if p.role in ("templates", "examples")]
    candidates = preferred or [p for p in candidates if p.role == "guidelines"]
    if not candidates:
        return None
    sizes = Counter((round(p.width, 1), round(p.height, 1)) for p in candidates)
    size = sizes.most_common(1)[0][0]
    selected = [p for p in candidates if (round(p.width, 1), round(p.height, 1)) == size]
    x: list[float] = []
    y: list[float] = []
    for page in selected:
        xs, ys = _edges(page, index)
        x.extend(sorted(xs))
        y.extend(sorted(ys))
    width, height = selected[0].width, selected[0].height
    columns, unit_w, x_score = _axis(x, width)
    rows, unit_h, y_score = _axis(y, height)
    return UnitGrid(
        format=format,
        width=width,
        height=height,
        pages=len(selected),
        roles=sorted({p.role for p in selected}),
        columns=columns,
        rows=rows,
        unit_w=unit_w,
        unit_h=unit_h,
        x_score=x_score,
        y_score=y_score,
    )


def _tallies(pages: list[PageVectors]) -> list[Tally]:
    groups: dict[tuple[Kind, str | None, float | None, Orientation | None], list[VectorMark]] = defaultdict(list)
    for page in pages:
        for mark in page.marks:
            width = round(mark.width, 2) if mark.width is not None else None
            groups[(mark.kind, mark.colour, width, mark.orientation)].append(mark)
    area = sum(p.width * p.height for p in pages)
    result = [
        Tally(
            kind=k,
            colour=c,
            width=w,
            orientation=o,
            count=len(marks),
            area_share=sum(abs(m.x1 - m.x0) * abs(m.y1 - m.y0) for m in marks) / area if k == "fill" else None,
        )
        for (k, c, w, o), marks in groups.items()
    ]
    return sorted(result, key=lambda t: (t.kind, -t.count, t.colour or "", t.width or 0, t.orientation or ""))


def measure_vectors(brand: Path) -> VectorReport:
    index = load_pages(brand)
    entries: dict[str, list[PageEntry]] = defaultdict(list)
    for entry in index.pages:
        entries[entry.file].append(entry)
    pages: list[PageVectors] = []
    for file, group in sorted(entries.items()):
        try:
            with pdfplumber.open(brand / file) as pdf:
                pages.extend(_page(entry, pdf.pages[entry.page - 1]) for entry in group)
        except (OSError, ValueError):
            continue
    pages.sort(key=lambda p: (p.file, p.page))
    formats: list[FormatVectors] = []
    for format in ("slides", "doc"):
        selected = [p for p in pages if p.format == format]
        if selected:
            formats.append(
                FormatVectors(format=format, grid=unit_grid(pages, index, format), tallies=_tallies(selected))
            )
    report = VectorReport(pages=pages, formats=formats)
    destination = brand / VECTORS
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return report
