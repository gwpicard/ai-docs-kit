"""A slides build writes a PowerPoint copy that looks like the PDF pages."""

import io
import re
import shutil
from functools import cached_property
from pathlib import Path

import pytest
from PIL import Image
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from tests.support.fixtures import fixture_path

from ai_docs_kit.cli import main
from ai_docs_kit.facts.layout import LayoutFacts
from ai_docs_kit.render.compose import Composition
from ai_docs_kit.store import field_index

EMU_PER_PT = 12700
TOLERANCE_PT = 1.0
DARK = 100
NOTE = "Say this aloud, slowly."


class Built:
    def __init__(self, file: Path, version: Path) -> None:
        self.file, self.version = file, version
        self.facts = LayoutFacts.model_validate_json((version / "layout.json").read_text(encoding="utf-8"))
        comp = Composition.model_validate_json((version / "composition.json").read_text(encoding="utf-8"))
        self.fields = field_index(self.facts, comp)
        self.pptx = version / f"{file.stem}.pptx"

    @cached_property
    def deck(self):
        assert self.pptx.is_file(), f"{self.pptx} was not written"
        return Presentation(str(self.pptx))


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Built:
    folder = tmp_path_factory.mktemp("pptx")
    file = folder / "deck.md"
    text = fixture_path("slides", "deck.md").read_text(encoding="utf-8")
    file.write_text(text.replace("A short deck for build tests.\n", f"A short deck for build tests.\n> note: {NOTE}\n"))
    assert main(["build", str(file)]) == 0
    return Built(file, folder / "deck.versions" / "v1")


def _by_name(slide) -> dict[str, object]:
    return {shape.name: shape for shape in slide.shapes if "/" in shape.name}


def test_build_writes_the_pptx_beside_the_pdf_and_into_the_version(built):
    out = built.file.parent / "build"
    assert (out / "deck.pptx").is_file()
    assert built.pptx.is_file()
    assert (out / "deck.pptx").read_bytes() == built.pptx.read_bytes()


def test_one_slide_per_pdf_page_at_the_pdf_page_size(built):
    pages = built.facts.pages
    assert len(built.deck.slides) == len(pages) >= 4
    for page in pages:
        assert built.deck.slide_width / EMU_PER_PT == pytest.approx(page.width, abs=TOLERANCE_PT)
        assert built.deck.slide_height / EMU_PER_PT == pytest.approx(page.height, abs=TOLERANCE_PT)


def test_each_slide_has_a_full_slide_picture_at_the_back(built):
    for slide in built.deck.slides:
        first = slide.shapes[0]
        assert first.shape_type == MSO_SHAPE_TYPE.PICTURE
        assert first.left / EMU_PER_PT == pytest.approx(0, abs=TOLERANCE_PT)
        assert first.top / EMU_PER_PT == pytest.approx(0, abs=TOLERANCE_PT)
        assert first.width == pytest.approx(built.deck.slide_width, abs=TOLERANCE_PT * EMU_PER_PT)
        assert first.height == pytest.approx(built.deck.slide_height, abs=TOLERANCE_PT * EMU_PER_PT)


def test_the_picture_is_the_hidden_text_render(built):
    checked = 0
    for page, slide in zip(built.facts.pages, built.deck.slides, strict=True):
        with Image.open(io.BytesIO(slide.shapes[0].image.blob)) as raw:
            image = raw.convert("L")
        scale = image.width / page.width
        for word in (w for w in built.facts.words if w.box.page == page.page):
            box = [round(v * scale) for v in (word.box.x0, word.box.y0, word.box.x1, word.box.y1)]
            crop = image.crop(tuple(box))
            assert crop.getextrema()[0] >= DARK, f"text of {word.text!r} is still drawn on slide {page.page}"
            checked += 1
    assert checked


def test_every_field_is_a_named_text_box_at_its_measured_box(built):
    expected = 0
    for entry, slide in zip(built.fields, built.deck.slides, strict=True):
        boxes = _by_name(slide)
        assert set(boxes) == {f"{f['section']}/{f['field']}" for f in entry["fields"]}
        for field in entry["fields"]:
            shape = boxes[f"{field['section']}/{field['field']}"]
            assert shape.has_text_frame
            for got, want in (
                (shape.left, field["x"]),
                (shape.top, field["y"]),
                (shape.width, field["w"]),
                (shape.height, field["h"]),
            ):
                assert got / EMU_PER_PT == pytest.approx(want, abs=TOLERANCE_PT), shape.name
            expected += 1
    assert expected >= 6


def _normal(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.split("+")[-1].split("-")[0].lower())


def test_text_boxes_use_the_theme_font_size_and_colour(built):
    checked = 0
    for entry, slide in zip(built.fields, built.deck.slides, strict=True):
        boxes = _by_name(slide)
        for field in entry["fields"]:
            shape = boxes[f"{field['section']}/{field['field']}"]
            words = [
                w
                for w in built.facts.words
                if w.section_id == field["section"]
                and w.role == field["role"]
                and field["x"] - 1 <= w.box.x0 <= field["x"] + field["w"] + 1
                and field["y"] - 1 <= w.box.y0 <= field["y"] + field["h"] + 1
            ]
            assert words, shape.name
            runs = [r for p in shape.text_frame.paragraphs for r in p.runs]
            assert runs, shape.name
            for run in runs:
                assert _normal(run.font.name or "") == _normal(words[0].font), shape.name
                assert run.font.size.pt == pytest.approx(words[0].size, abs=0.5), shape.name
                assert str(run.font.color.rgb) == words[0].colour.lstrip("#").upper(), shape.name
                checked += 1
    assert checked


def test_text_per_section_equals_the_layout_facts(built):
    seen = set()
    for entry, slide in zip(built.fields, built.deck.slides, strict=True):
        for section in {f["section"] for f in entry["fields"]}:
            got = " ".join(
                shape.text_frame.text for name, shape in _by_name(slide).items() if name.startswith(f"{section}/")
            ).split()
            inside = [
                w.text
                for w in built.facts.words
                if w.section_id == section
                and w.box.page == entry["page"]
                and any(
                    f["section"] == section
                    and f["x"] <= (w.box.x0 + w.box.x1) / 2 <= f["x"] + f["w"]
                    and f["y"] <= (w.box.y0 + w.box.y1) / 2 <= f["y"] + f["h"]
                    for f in entry["fields"]
                )
            ]
            assert got == inside, section
            seen.add(section)
    assert {"cover", "agenda", "closing"} <= seen


def test_speaker_notes_hold_the_note_field_when_there_is_one(built):
    notes = {}
    for entry, slide in zip(built.fields, built.deck.slides, strict=True):
        text = slide.notes_slide.notes_text_frame.text if slide.has_notes_slide else ""
        for section in {f["section"] for f in entry["fields"]}:
            notes[section] = text
    assert NOTE in notes["cover"]
    assert NOTE not in notes["agenda"] and NOTE not in notes["closing"]


def test_a_document_build_writes_no_pptx(tmp_path, capsys):
    file = tmp_path / "report.md"
    shutil.copyfile(fixture_path("doc", "report.md"), file)
    assert main(["build", str(file)]) == 0
    version = Path(capsys.readouterr().out.strip().splitlines()[-1])
    assert not list(version.glob("*.pptx")) and not list((tmp_path / "build").glob("*.pptx"))
