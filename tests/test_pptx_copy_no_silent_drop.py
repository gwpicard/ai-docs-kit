"""The PowerPoint copy never drops words or notes silently; a slide/page mismatch fails the build with a message."""

import re

from pptx import Presentation

import ai_docs_kit.render.pptx_copy as pptx_copy
from ai_docs_kit.cli import main

DECK = """---
doctype: pitch-deck
format: slides
title: Readout
---

::: {#cover intent=cover}
## Readout
A short deck.
> note: Note one.
:::

::: {#blank intent=closing}
> note: Note two.
:::

::: {#statement intent=statement}
## A clear direction
Simple ideas make a strong story.
> note: Note three.
:::

::: {#closing intent=closing}
## Thank you
> note: Note four.
:::
"""

NOTES = ["Note one.", "Note two.", "Note three.", "Note four."]


def _build(tmp_path):
    file = tmp_path / "deck.md"
    file.write_text(DECK, encoding="utf-8")
    code = main(["build", str(file)])
    return code, tmp_path / "deck.versions" / "v1" / "deck.pptx"


def _notes(deck) -> list[str | None]:
    return [s.notes_slide.notes_text_frame.text if s.has_notes_slide else None for s in deck.slides]


def _text(slide) -> str:
    return " ".join(s.text_frame.text for s in slide.shapes if s.has_text_frame)


def _patch_write(monkeypatch, change) -> None:
    real = pptx_copy.write_pptx

    def wrapped(path, *, facts, comp, **rest):
        facts, comp = change(facts, comp)
        return real(path, facts=facts, comp=comp, **rest)

    monkeypatch.setattr(pptx_copy, "write_pptx", wrapped)


def test_each_note_lands_on_its_own_slide_when_the_second_section_has_no_words(tmp_path):
    code, pptx = _build(tmp_path)
    assert code == 0
    assert _notes(Presentation(str(pptx))) == NOTES


def test_words_without_a_section_id_get_a_page_text_box(tmp_path, monkeypatch):
    seen: dict[str, int] = {}

    def strip(facts, comp):
        stripped = [w for w in facts.words if w.section_id == "statement"]
        seen["page"] = stripped[0].box.page
        seen["words"] = len(stripped)
        words = [w.model_copy(update={"section_id": None}) if w.section_id == "statement" else w for w in facts.words]
        return facts.model_copy(update={"words": words}), comp

    _patch_write(monkeypatch, strip)
    code, pptx = _build(tmp_path)
    assert code == 0
    slide = Presentation(str(pptx)).slides[seen["page"] - 1]
    names = [shape.name for shape in slide.shapes]
    assert f"{seen['page']}/text" in names
    text = _text(slide)
    for word in ["A", "clear", "direction", "Simple", "ideas", "make", "a", "strong", "story."]:
        assert re.search(rf"(?<!\S){re.escape(word)}(?!\S)", text), f"{word!r} is missing from the copy"


def test_slide_page_mismatch_fails_the_build_with_one_line(tmp_path, monkeypatch, capsys):
    real = pptx_copy.field_index
    monkeypatch.setattr(pptx_copy, "field_index", lambda facts, comp=None: real(facts, comp)[:-1])
    code, _ = _build(tmp_path)
    err = capsys.readouterr().err
    assert code == 1
    assert "Traceback" not in err
    lines = [line for line in err.splitlines() if line.strip()]
    assert len(lines) == 1, err
    assert "3" in lines[0] and "4" in lines[0], lines[0]


def test_pins_current_notes_when_slide_count_differs_from_section_count(tmp_path, monkeypatch):
    """#54: four pages, three sections; the build succeeds and notes follow the words of their section."""

    def drop_blank(facts, comp):
        sections = [s for s in comp.sections if s.id != "blank"]
        return facts, comp.model_copy(update={"sections": sections})

    _patch_write(monkeypatch, drop_blank)
    code, pptx = _build(tmp_path)
    assert code == 0
    deck = Presentation(str(pptx))
    assert len(deck.slides) == 4
    assert [n or None for n in _notes(deck)] == ["Note one.", None, "Note three.", "Note four."]
