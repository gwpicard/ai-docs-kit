"""Added native table text survives different cell layouts and shape orders."""

import json
import shutil

import pytest
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


@pytest.mark.parametrize(
    ("cells", "box_first"),
    [
        pytest.param(
            (("", "First row detail", ""), ("Second row start", "", "Closing detail\nNext paragraph")),
            False,
            id="wide-table-before-box",
        ),
        pytest.param(
            (("Opening detail", ""), ("", "Middle detail\nFurther explanation"), ("", "Final row detail")),
            True,
            id="tall-table-after-box",
        ),
    ],
)
def test_added_table_reports_every_populated_cell(tmp_path, capsys, cells, box_first):
    source = tmp_path / "deck.md"
    source.write_text(SOURCE, encoding="utf-8")
    assert main(["build", str(source)]) == 0
    version = tmp_path / "deck.versions" / "v1"
    copy = tmp_path / "deck-reviewed.pptx"
    shutil.copyfile(version / "deck.pptx", copy)
    deck = Presentation(str(copy))
    slide = deck.slides[0]
    box_text = "An added text box still reaches the review plan."
    if box_first:
        slide.shapes.add_textbox(Inches(1), Inches(5), Inches(5), Inches(1)).text = box_text
    table = slide.shapes.add_table(len(cells), len(cells[0]), Inches(1), Inches(2), Inches(5), Inches(2)).table
    for row_index, row in enumerate(cells):
        for column_index, text in enumerate(row):
            table.cell(row_index, column_index).text = text
    if not box_first:
        slide.shapes.add_textbox(Inches(1), Inches(5), Inches(5), Inches(1)).text = box_text
    deck.save(str(copy))
    capsys.readouterr()

    assert main(["review", "read", str(copy)]) == 0
    plan = json.loads((version / "review-plan.json").read_text(encoding="utf-8"))
    unplaced = "\n".join(item["text"] for item in plan["confirm"] if item["kind"] == "unplaced")
    assert box_text in unplaced
    missing = [text for row in cells for text in row if text and text not in unplaced]
    assert not missing, f"The review plan lost table cell text {missing}: {plan}"
    assert plan["sections"]["alpha"]["fields"] == {}
    assert plan["sections"]["alpha"]["wording"] is None
    assert plan["sections"]["alpha"]["owner"] is None
    assert not any(item["kind"] in ("delete", "reorder") for item in plan["confirm"])
