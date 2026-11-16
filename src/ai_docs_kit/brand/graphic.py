"""Trace and measure a brand's signature graphic."""

from pathlib import Path
from typing import Literal

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, Field

from ai_docs_kit.brand.pages import load_manifest, load_pages
from ai_docs_kit.brand.vectors import VECTORS, UnitGrid, VectorReport
from ai_docs_kit.brand.workspace import BrandError
from ai_docs_kit.facts.models import Shape
from ai_docs_kit.facts.pdf import PdfPlumberFacts
from ai_docs_kit.model.source import Format
from ai_docs_kit.theme import load_theme

GRAPHIC = Path("theme/graphics/signature.yaml")
SNAP = 0.75


class Tile(BaseModel):
    col: int = Field(ge=0)
    row: int = Field(ge=0)
    cols: int = Field(ge=1)
    rows: int = Field(ge=1)
    colour: str
    role: str | None


class TracedPage(BaseModel):
    file: str
    page: int
    sha256: str
    tiles: list[Tile]
    untraced: int


class Signature(BaseModel):
    coverage: float
    tiles: int
    clusters: int
    regions: list[float]
    margin_cols: int
    margin_rows: int
    sizes: list[tuple[int, int]]
    colours: list[str]


class SignatureRange(BaseModel):
    coverage: tuple[float, float]
    tiles: tuple[int, int]
    clusters: tuple[int, int]
    regions_max: list[float]
    margin_cols: int
    margin_rows: int
    sizes: list[tuple[int, int]]
    colours: list[str]


class SignatureGraphic(BaseModel):
    schema_version: int = 1
    label: Literal["measured"] = "measured"
    format: Format
    grid: UnitGrid
    pages: list[TracedPage]
    signatures: list[Signature]
    range: SignatureRange


def _tile(shape: Shape, grid: UnitGrid, roles: dict[str, str]) -> Tile | None:
    assert grid.unit_w is not None and grid.unit_h is not None
    assert grid.columns is not None and grid.rows is not None
    box = shape.box
    edges = (box.x0, box.y0, box.x1, box.y1)
    units = (grid.unit_w, grid.unit_h, grid.unit_w, grid.unit_h)
    snapped = tuple(round(edge / unit) for edge, unit in zip(edges, units, strict=True))
    if any(abs(edge - n * unit) > SNAP for edge, unit, n in zip(edges, units, snapped, strict=True)):
        return None
    x0, y0, x1, y1 = snapped
    if box.x0 < 0 or box.y0 < 0 or box.x1 > grid.width or box.y1 > grid.height:
        return None
    if not (0 <= x0 < x1 <= grid.columns and 0 <= y0 < y1 <= grid.rows):
        return None
    assert shape.fill is not None
    role = next((name for name, colour in roles.items() if colour.upper() == shape.fill.upper()), None)
    return Tile(col=x0, row=y0, cols=x1 - x0, rows=y1 - y0, colour=shape.fill, role=role)


def _ignored(shape: Shape, width: float, height: float) -> bool:
    box = shape.box
    w, h = abs(box.x1 - box.x0), abs(box.y1 - box.y0)
    return w * h >= 0.95 * width * height or (shape.kind == "rect" and min(w, h) <= 3 and max(w, h) >= 10 * min(w, h))


def trace_pdf_page(pdf: Path, page: int, grid: UnitGrid, roles: dict[str, str]) -> tuple[list[Tile], int]:
    facts = PdfPlumberFacts().extract(pdf)[page - 1]
    tiles: list[Tile] = []
    untraced = 0
    for shape in facts.shapes:
        if shape.fill is None or _ignored(shape, facts.width, facts.height):
            continue
        tile = _tile(shape, grid, roles) if shape.kind == "rect" else None
        if tile is None:
            untraced += 1
        else:
            tiles.append(tile)
    return sorted(tiles, key=lambda tile: (tile.row, tile.col)), untraced


def _clusters(cells: set[tuple[int, int]]) -> int:
    remaining = cells.copy()
    count = 0
    while remaining:
        count += 1
        stack = [remaining.pop()]
        while stack:
            row, col = stack.pop()
            for neighbour in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
                if neighbour in remaining:
                    remaining.remove(neighbour)
                    stack.append(neighbour)
    return count


def measure(tiles: list[Tile], grid: UnitGrid) -> Signature:
    assert grid.columns is not None and grid.rows is not None
    cols, rows = grid.columns, grid.rows
    cells = {
        (row, col)
        for tile in tiles
        for row in range(tile.row, tile.row + tile.rows)
        for col in range(tile.col, tile.col + tile.cols)
    }
    totals = [0] * 9
    covered = [0] * 9
    for row in range(rows):
        for col in range(cols):
            region = min(2, row * 3 // rows) * 3 + min(2, col * 3 // cols)
            totals[region] += 1
            covered[region] += (row, col) in cells
    return Signature(
        coverage=round(len(cells) / (cols * rows), 4),
        tiles=len(tiles),
        clusters=_clusters(cells),
        regions=[round(n / total, 4) if total else 0 for n, total in zip(covered, totals, strict=True)],
        margin_cols=min((min(col, cols - 1 - col) for _, col in cells), default=cols),
        margin_rows=min((min(row, rows - 1 - row) for row, _ in cells), default=rows),
        sizes=sorted({(tile.cols, tile.rows) for tile in tiles}),
        colours=sorted({tile.colour for tile in tiles}),
    )


def signature_range(signatures: list[Signature]) -> SignatureRange:
    return SignatureRange(
        coverage=(min(s.coverage for s in signatures), max(s.coverage for s in signatures)),
        tiles=(min(s.tiles for s in signatures), max(s.tiles for s in signatures)),
        clusters=(min(s.clusters for s in signatures), max(s.clusters for s in signatures)),
        regions_max=[max(s.regions[i] for s in signatures) for i in range(9)],
        margin_cols=min(s.margin_cols for s in signatures),
        margin_rows=min(s.margin_rows for s in signatures),
        sizes=sorted({size for s in signatures for size in s.sizes}),
        colours=sorted({colour for s in signatures for colour in s.colours}),
    )


def trace_graphic(brand: Path, pages: list[tuple[str, int]]) -> SignatureGraphic:
    if not pages:
        raise BrandError("No pages specified")
    vector_path = brand / VECTORS
    if not vector_path.exists():
        raise BrandError("Run ai_docs_kit brand vectors first")
    report = VectorReport.model_validate_json(vector_path.read_text(encoding="utf-8"))
    manifest = load_manifest(brand)
    index = load_pages(brand)
    roles = load_theme(brand / "theme").tokens.colour.roles
    traced: list[TracedPage] = []
    signatures: list[Signature] = []
    selected_grid: UnitGrid | None = None
    for file, page in pages:
        reference = f"{file} p{page}"
        entry = next((item for item in manifest.files if item.path == file), None)
        indexed = next((item for item in index.pages if item.file == file and item.page == page), None)
        if entry is None or entry.type != "pdf" or entry.unread is not None or indexed is None or page < 1:
            raise BrandError(f"{reference}: missing, unreadable or out of range")
        grid = next((item.grid for item in report.formats if item.format == indexed.format), None)
        if grid is None or any(
            value is None or value <= 0 for value in (grid.columns, grid.rows, grid.unit_w, grid.unit_h)
        ):
            raise BrandError(f"{reference}: no measured grid")
        if selected_grid is not None and grid.format != selected_grid.format:
            raise BrandError(f"{reference}: pages have different formats")
        selected_grid = grid
        try:
            tiles, untraced = trace_pdf_page(brand / file, page, grid, roles)
        except Exception as error:
            raise BrandError(f"{reference}: could not read PDF") from error
        if not tiles:
            raise BrandError(f"{reference}: no tiles")
        traced.append(TracedPage(file=file, page=page, sha256=entry.sha256, tiles=tiles, untraced=untraced))
        signatures.append(measure(tiles, grid))
    assert selected_grid is not None
    return SignatureGraphic(
        format=selected_grid.format,
        grid=selected_grid,
        pages=traced,
        signatures=signatures,
        range=signature_range(signatures),
    )


def save_graphic(brand: Path, graphic: SignatureGraphic) -> None:
    path = brand / GRAPHIC
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(graphic.model_dump(mode="json"), sort_keys=False), encoding="utf-8")


def load_graphic(brand: Path) -> SignatureGraphic | None:
    path = brand / GRAPHIC
    return SignatureGraphic.model_validate(yaml.safe_load(path.read_text(encoding="utf-8"))) if path.exists() else None
