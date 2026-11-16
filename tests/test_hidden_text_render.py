"""A build with its text hidden keeps the layout identical and draws no text."""

import inspect
import tempfile
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]
from PIL import Image, ImageChops

from ai_docs_kit.facts.layout import layout_facts
from ai_docs_kit.facts.raster import DEFAULT_SCALE, PdfiumRasteriser
from ai_docs_kit.model import Document, Section
from ai_docs_kit.render.components import all_manifests
from ai_docs_kit.render.compose import assemble, compose, font_paths
from ai_docs_kit.render.typst import compile_pdf
from ai_docs_kit.testing.golden import _fixture_assets
from ai_docs_kit.theme import neutral_theme

FIXTURES = Path(__file__).parent / "fixtures" / "components"
NAMES = sorted(path.name.removesuffix(".yaml") for path in FIXTURES.glob("*.yaml"))
TOLERANCE_PT = 0.01
DARK = 100


def _render_both(name: str, workdir: Path):
    data = yaml.safe_load((FIXTURES / f"{name}.yaml").read_text(encoding="utf-8"))
    section = Section.model_validate(data)
    manifest = all_manifests().get(section.component or name)
    doc = Document(front={}, format=manifest.format if manifest else "slides", sections=[section])
    dest = workdir / name
    main = assemble(compose(doc, assets=_fixture_assets(section, workdir)), dest, theme=neutral_theme())
    fonts = font_paths(dest)
    shown, hidden = dest / "shown.pdf", dest / "hidden.pdf"
    compile_pdf(main, dest, shown, fonts)
    compile_pdf(main, dest, hidden, fonts, hide_text=True)
    return (
        layout_facts(shown, main, dest, font_paths=fonts),
        layout_facts(hidden, main, dest, font_paths=fonts),
        PdfiumRasteriser().render(shown, dest / "shown"),
        PdfiumRasteriser().render(hidden, dest / "hidden"),
    )


def test_hide_text_is_off_by_default():
    parameter = inspect.signature(compile_pdf).parameters["hide_text"]
    assert parameter.default is False


@pytest.mark.parametrize("name", NAMES)
def test_hidden_text_keeps_every_box(name):
    with tempfile.TemporaryDirectory() as folder:
        shown, hidden, _, _ = _render_both(name, Path(folder))
    assert len(hidden.marks) == len(shown.marks)
    assert len(hidden.words) == len(shown.words)
    for a, b in zip(shown.marks, hidden.marks, strict=True):
        assert a.model_dump() == pytest.approx(b.model_dump(), abs=TOLERANCE_PT)
    for a, b in zip(shown.words, hidden.words, strict=True):
        assert a.text == b.text and a.box.page == b.box.page
        for key in ("x0", "y0", "x1", "y1"):
            assert abs(getattr(a.box, key) - getattr(b.box, key)) <= TOLERANCE_PT, (a.text, key)


@pytest.mark.parametrize("name", ["body", "cards"])
def test_hidden_text_changes_only_text_pixels(name):
    with tempfile.TemporaryDirectory() as folder:
        shown, hidden, shown_pngs, hidden_pngs = _render_both(name, Path(folder))
        assert len(shown_pngs) == len(hidden_pngs)
        saw_dark_text = False
        for page, (a_png, b_png) in enumerate(zip(shown_pngs, hidden_pngs, strict=True), start=1):
            with Image.open(a_png) as a, Image.open(b_png) as b:
                shown_img, hidden_img = a.convert("RGB"), b.convert("RGB")
            inside = Image.new("L", shown_img.size, 0)
            for word in shown.words:
                if word.box.page != page:
                    continue
                box = tuple(round(v * DEFAULT_SCALE) for v in (word.box.x0, word.box.y0, word.box.x1, word.box.y1))
                inside.paste(255, box)
            outside_diff = ImageChops.difference(shown_img, hidden_img).convert("L")
            outside_diff = ImageChops.multiply(outside_diff, ImageChops.invert(inside))
            assert outside_diff.getbbox() is None, "pixels outside text boxes changed"
            dark = hidden_img.convert("L").point(lambda v: 255 if v < DARK else 0)
            assert ImageChops.multiply(dark, inside).getbbox() is None, "dark text pixels remain"
            shown_dark = shown_img.convert("L").point(lambda v: 255 if v < DARK else 0)
            saw_dark_text |= ImageChops.multiply(shown_dark, inside).getbbox() is not None
        assert saw_dark_text, "the normal render has no dark text to hide"
