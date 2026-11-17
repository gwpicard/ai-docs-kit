"""A speaker note survives into the PowerPoint copy even when its section has no words on the slide."""

from pptx import Presentation

from ai_docs_kit.cli import main

DECK = """---
doctype: pitch-deck
format: slides
title: Readout
---

::: {#cover intent=cover}
## Readout
A short deck for build tests.
:::

::: {#closing intent=closing}
> note: Close warmly.
:::
"""


def test_note_of_a_wordless_section_reaches_its_slide(tmp_path):
    file = tmp_path / "deck.md"
    file.write_text(DECK, encoding="utf-8")
    assert main(["build", str(file)]) == 0
    deck = Presentation(str(tmp_path / "deck.versions" / "v1" / "deck.pptx"))
    slide = deck.slides[1]
    assert slide.has_notes_slide, "the closing slide lost its speaker note"
    assert slide.notes_slide.notes_text_frame.text == "Close warmly."
