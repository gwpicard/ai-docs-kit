"""Duplicating a named box must not overwrite the original field and lose the added words."""

import copy
import json

from pptx import Presentation

from ai_docs_kit.cli import main


def test_duplicate_named_box_is_reported_as_unplaced_text(tmp_path):
    source = tmp_path / "deck.md"
    source.write_text(
        "---\ndoctype: pitch-deck\nformat: slides\ntitle: Readout\n---\n\n"
        '::: {#cover .section intent="cover"}\n## Readout\n\n'
        "Original subtitle.\n:::\n",
        encoding="utf-8",
    )
    assert main(["build", str(source)]) == 0
    version = tmp_path / "deck.versions" / "v1"
    deck = Presentation(str(version / "deck.pptx"))
    slide = deck.slides[0]
    original = next(shape for shape in slide.shapes if shape.name == "cover/paragraphs[0]")
    duplicate = copy.deepcopy(original._element)
    properties = duplicate.find(".//{http://schemas.openxmlformats.org/presentationml/2006/main}cNvPr")
    properties.set("id", str(max(shape.shape_id for shape in slide.shapes) + 1))
    slide.shapes._spTree.insert_element_before(duplicate, "p:extLst")
    added = next(shape for shape in slide.shapes if shape._element is duplicate)
    added.text = "An extra note needs a section."
    reviewed = tmp_path / "deck-reviewed.pptx"
    deck.save(str(reviewed))

    assert main(["review", "read", str(reviewed)]) == 0
    plan = json.loads((version / "review-plan.json").read_text(encoding="utf-8"))
    unplaced = [item["text"] for item in plan["confirm"] if item["kind"] == "unplaced"]
    assert any("An extra note needs a section." in text for text in unplaced), (
        f"Duplicating a box overwrote the original field instead of preserving the extra text: {plan}"
    )
    assert "paragraphs[0]" not in plan["sections"]["cover"]["fields"]
