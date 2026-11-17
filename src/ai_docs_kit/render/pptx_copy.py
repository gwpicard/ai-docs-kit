"""The PowerPoint copy of a slides build: the page picture with its text hidden, and a native box per text field."""

import tempfile
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE
from pptx.util import Emu, Pt

from ai_docs_kit.facts.layout import LayoutFacts, PlacedWord
from ai_docs_kit.facts.raster import PdfiumRasteriser
from ai_docs_kit.model import Document
from ai_docs_kit.render.compose import Composition
from ai_docs_kit.render.typst import compile_pdf
from ai_docs_kit.store import field_index

EMU_PER_PT = 12700
BLANK_LAYOUT = 6
LOOSE_FIELD = "text"


def _emu(points: float) -> Emu:
    return Emu(round(points * EMU_PER_PT))


def _inside(word: PlacedWord, field: dict[str, Any]) -> bool:
    x, y = (word.box.x0 + word.box.x1) / 2, (word.box.y0 + word.box.y1) / 2
    return bool(field["x"] <= x <= field["x"] + field["w"] and field["y"] <= y <= field["y"] + field["h"])


def _lines(words: list[PlacedWord]) -> list[list[PlacedWord]]:
    """Group words into lines by baseline, keeping the order they have in the facts."""
    lines: list[list[PlacedWord]] = []
    for word in words:
        if lines and abs(lines[-1][0].baseline - word.baseline) < word.size / 2:
            lines[-1].append(word)
        else:
            lines.append([word])
    return lines


def _family(font: str) -> str:
    """`ABCDEF+Inter-Bold` is the font `Inter`: drop the subset prefix and the style."""
    return font.split("+")[-1].split("-")[0]


def _add_box(slide: Any, name: str, words: list[PlacedWord], box: tuple[float, float, float, float]) -> None:
    x, y, w, h = box
    shape = slide.shapes.add_textbox(_emu(x), _emu(y), _emu(w), _emu(h))
    shape.name = name
    frame = shape.text_frame
    frame.word_wrap = False
    frame.auto_size = MSO_AUTO_SIZE.NONE
    frame.vertical_anchor = MSO_ANCHOR.TOP
    frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
    first = words[0]
    for index, line in enumerate(_lines(words)):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        run = paragraph.add_run()
        run.text = " ".join(word.text for word in line)
        run.font.name = _family(first.font)
        run.font.size = Pt(first.size)
        if first.colour:
            run.font.color.rgb = RGBColor.from_string(first.colour.lstrip("#").upper())  # type: ignore[no-untyped-call]


def _bounds(words: list[PlacedWord]) -> tuple[float, float, float, float]:
    x, y = min(w.box.x0 for w in words), min(w.box.y0 for w in words)
    return x, y, max(w.box.x1 for w in words) - x, max(w.box.y1 for w in words) - y


def _fill_slide(slide: Any, entry: dict[str, Any], words: list[PlacedWord], notes: list[str]) -> None:
    fields = entry["fields"]
    owned: dict[int, list[PlacedWord]] = {i: [] for i in range(len(fields))}
    loose: dict[str, list[PlacedWord]] = {}
    for word in words:
        homes = [i for i, f in enumerate(fields) if f["section"] == word.section_id and _inside(word, f)]
        if homes:
            owned[min(homes, key=lambda i: fields[i]["w"] * fields[i]["h"])].append(word)
        elif word.section_id:
            loose.setdefault(word.section_id, []).append(word)
    for i, field in enumerate(fields):
        if owned[i]:
            box = (field["x"], field["y"], field["w"], field["h"])
            _add_box(slide, f"{field['section']}/{field['field']}", owned[i], box)
    for section, rest in loose.items():
        _add_box(slide, f"{section}/{LOOSE_FIELD}", rest, _bounds(rest))
    if notes:
        slide.notes_slide.notes_text_frame.text = "\n".join(notes)


def write_pptx(
    path: Path,
    *,
    facts: LayoutFacts,
    comp: Composition,
    doc: Document,
    main: Path,
    render: Path,
    font_paths: list[Path],
) -> Path:
    """Write the editable slides copy to `path`: one slide per PDF page, at the PDF page size."""
    notes = {s.id: s.note for s in doc.sections if s.id and s.note}
    deck = Presentation()
    deck.slide_width, deck.slide_height = _emu(facts.pages[0].width), _emu(facts.pages[0].height)
    with tempfile.TemporaryDirectory(prefix="pptx-") as scratch:
        hidden = Path(scratch) / "hidden.pdf"
        compile_pdf(main, render, hidden, font_paths, hide_text=True)
        pictures = PdfiumRasteriser().render(hidden, Path(scratch) / "pages")
        for entry, picture in zip(field_index(facts, comp), pictures, strict=True):
            slide = deck.slides.add_slide(deck.slide_layouts[BLANK_LAYOUT])
            slide.shapes.add_picture(str(picture), 0, 0, deck.slide_width, deck.slide_height)
            words = [w for w in facts.words if w.box.page == entry["page"]]
            present = {w.section_id for w in words}
            slide_notes = [notes[s.id] for s in comp.sections if s.id in present and s.id in notes]
            _fill_slide(slide, entry, words, slide_notes)
        deck.save(str(path))
    return path
