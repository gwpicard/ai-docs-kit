"""Text added in a native PowerPoint table must reach the review plan as unplaced."""

import json
import shutil

from pptx import Presentation
from pptx.util import Inches

from ai_docs_kit.cli import main

SOURCE = """---
doctype: pitch-deck
format: slides
title: Readout
---

::: {#alpha .section intent="statement"}
## The direction

The original sentence remains unchanged.
:::
"""


def test_added_native_table_text_is_reported_as_unplaced(tmp_path, capsys):
    source = tmp_path / "deck.md"
    source.write_text(SOURCE, encoding="utf-8")
    assert main(["build", str(source)]) == 0
    version = tmp_path / "deck.versions" / "v1"
    copy = tmp_path / "deck-reviewed.pptx"
    shutil.copyfile(version / "deck.pptx", copy)
    deck = Presentation(str(copy))
    slide = deck.slides[0]
    table = slide.shapes.add_table(1, 1, Inches(1), Inches(3), Inches(5), Inches(1)).table
    table.cell(0, 0).text = "A table added by the reviewer."
    # A normal untagged text box provides a control for the same review behaviour.
    box = slide.shapes.add_textbox(Inches(1), Inches(4), Inches(5), Inches(1))
    box.text = "A text box added by the reviewer."
    deck.save(str(copy))
    capsys.readouterr()

    assert main(["review", "read", str(copy)]) == 0
    plan = json.loads((version / "review-plan.json").read_text(encoding="utf-8"))
    unplaced = "\n".join(item["text"] for item in plan["confirm"] if item["kind"] == "unplaced")
    assert box.text in unplaced
    assert table.cell(0, 0).text in unplaced, f"The review reader lost the added table: {plan}"
