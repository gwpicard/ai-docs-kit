"""Render a fixed specimen of the components a doctype can use."""

import hashlib
import shutil
from pathlib import Path

import yaml  # type: ignore[import-untyped]
from PIL import Image, ImageDraw
from pydantic import BaseModel, ValidationError

from ai_docs_kit.brand.pages import WORK
from ai_docs_kit.brand.work import work_dir
from ai_docs_kit.doctypes import Doctype, walk
from ai_docs_kit.facts import PdfiumRasteriser
from ai_docs_kit.facts.layout import layout_facts
from ai_docs_kit.facts.sheets import contact_sheet
from ai_docs_kit.model import Document, Format, Section
from ai_docs_kit.render.components import all_manifests
from ai_docs_kit.render.compose import assemble, compose, font_paths
from ai_docs_kit.render.marks import Mark, SectionMark
from ai_docs_kit.render.typst import compile_pdf
from ai_docs_kit.theme import load_theme


class SpecimenPage(BaseModel):
    page: int
    png: str
    components: list[str]


class SpecimenRender(BaseModel):
    doctype: str
    format: Format
    theme_root: str
    theme_sha256: str
    folder: str
    pdf: str
    sheet: str
    pages: list[SpecimenPage]


def specimen_sections(fmt: Format) -> list[Section]:
    data = yaml.safe_load(Path(__file__).with_name("specimen.yaml").read_text(encoding="utf-8"))
    sections = [Section.model_validate(section) for section in data["sections"]]
    manifests = all_manifests()
    for name in manifests:
        if not any(section.component == name for section in sections):
            raise ValueError(f"Missing specimen section for {name}")
    return [
        section for section in sections if section.component in manifests and manifests[section.component].format == fmt
    ]


def specimen_document(doctype: Doctype) -> Document:
    intents = {entry.intent for entry in walk(doctype.outline)}
    manifests = all_manifests()
    sections = specimen_sections(doctype.format)
    if "any" not in intents:
        sections = [s for s in sections if s.component and intents.intersection(manifests[s.component].intents)]
    return Document(front={"title": "Specimen", "doctype": doctype.name}, format=doctype.format, sections=sections)


def _digest(root: Path) -> str:
    return hashlib.sha256((root / "theme.yaml").read_bytes() + (root / "tokens.yaml").read_bytes()).hexdigest()


def _cached(folder: Path) -> SpecimenRender | None:
    try:
        return SpecimenRender.model_validate_json((folder / "specimen.json").read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError):
        return None


def specimen_for(brand: Path, doctype_name: str, *, theme_root: Path | None = None) -> SpecimenRender | None:
    root = (theme_root or brand / "theme").resolve()
    load_theme(root)
    return _cached(brand / WORK / "specimens" / doctype_name / _digest(root)[:12])


def _picture(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1200, 675), "#dce8e8")
    draw = ImageDraw.Draw(image)
    draw.polygon([(0, 500), (350, 230), (650, 500)], fill="#6c9892")
    draw.polygon([(400, 675), (850, 260), (1200, 600), (1200, 675)], fill="#3e706d")
    image.save(path)


def _pages(brand: Path, pngs: list[Path], doc: Document, marks: list[Mark]) -> list[SpecimenPage]:
    starts = {m.id: m.page for m in marks if isinstance(m, SectionMark) and m.edge == "start"}
    ends = {m.id: m.page for m in marks if isinstance(m, SectionMark) and m.edge == "end"}
    return [
        SpecimenPage(
            page=i,
            png=path.relative_to(brand).as_posix(),
            components=[
                s.component
                for s in doc.sections
                if s.component and s.id in starts and s.id in ends and starts[s.id] <= i <= ends[s.id]
            ],
        )
        for i, path in enumerate(pngs, 1)
    ]


def render_specimen(brand: Path, doctype: Doctype, *, theme_root: Path | None = None) -> SpecimenRender:
    brand = brand.resolve()
    root = (theme_root or brand / "theme").resolve()
    theme = load_theme(root)
    digest = _digest(root)
    folder = work_dir(brand) / "specimens" / doctype.name / digest[:12]
    cached = _cached(folder)
    if cached is not None:
        return cached
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    assets = folder / "assets"
    _picture(assets / "specimen.png")
    doc = specimen_document(doctype)
    comp = compose(doc, assets=[assets])
    render_dir = folder / "render"
    main = assemble(comp, render_dir, theme=theme)
    pdf = folder / "specimen.pdf"
    fonts = font_paths(render_dir)
    compile_pdf(main, render_dir, pdf, fonts)
    facts = layout_facts(pdf, main, render_dir, font_paths=fonts)
    pngs = PdfiumRasteriser().render(pdf, folder / "pages")
    pages = _pages(brand, pngs, doc, facts.marks)
    sheet = folder / "sheet.png"
    contact_sheet(pngs, [f"{p.page} {' '.join(p.components)}" for p in pages], sheet)
    result = SpecimenRender(
        doctype=doctype.name,
        format=doctype.format,
        theme_root=str(root),
        theme_sha256=digest,
        folder=folder.relative_to(brand).as_posix(),
        pdf=pdf.relative_to(brand).as_posix(),
        sheet=sheet.relative_to(brand).as_posix(),
        pages=pages,
    )
    (folder / "specimen.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return result


def component_pages(render: SpecimenRender) -> dict[str, int]:
    result: dict[str, int] = {}
    for page in render.pages:
        for component in page.components:
            result.setdefault(component, page.page)
    return result
