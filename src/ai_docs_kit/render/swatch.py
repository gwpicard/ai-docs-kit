import shutil
from pathlib import Path

from pydantic import BaseModel

from ai_docs_kit.facts.layout import LayoutFacts, layout_facts
from ai_docs_kit.facts.raster import PdfiumRasteriser
from ai_docs_kit.model import Document
from ai_docs_kit.render.compose import assemble, compose, font_paths
from ai_docs_kit.render.typst import compile_pdf
from ai_docs_kit.theme import Theme


class SwatchRender(BaseModel):
    pdf: Path
    main: Path
    facts: LayoutFacts
    pngs: list[Path]


def _alone(doc: Document, section_id: str) -> Document:
    for section in doc.sections:
        if section.id == section_id:
            return doc.model_copy(update={"sections": [section]})
    raise KeyError(f"no section with id {section_id!r}")


def swatch(
    doc: Document, section_id: str, workdir: Path, theme: Theme | None = None, *, assets: list[Path] | None = None
) -> SwatchRender:
    """Render one section of `doc` alone on its format's page, in `workdir / swatch-<id>`, with `theme` if given."""
    single = _alone(doc, section_id)
    dest = workdir / f"swatch-{section_id}"
    if dest.exists():
        shutil.rmtree(dest)
    comp = compose(single, assets=assets).model_copy(update={"front": {}, "version_date": None})
    main = assemble(comp, dest, theme=theme)
    fonts = font_paths(dest)
    pdf = dest / "swatch.pdf"
    compile_pdf(main, dest, pdf, fonts)
    facts = layout_facts(pdf, main, dest, font_paths=fonts)
    pngs = PdfiumRasteriser().render(pdf, dest / "pages")
    return SwatchRender(pdf=pdf, main=main, facts=facts, pngs=pngs)
