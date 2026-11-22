"""Repeated field names preserve each extra box alongside a valid wording edit."""

import copy
import json
from collections import Counter

import pytest
from pptx import Presentation

from ai_docs_kit.cli import main


@pytest.mark.parametrize(
    ("section", "field", "extra_words"),
    [
        (
            "cover",
            "paragraphs[0]",
            ("First extra note.", "Second extra note.", "First extra note."),
        ),
        (
            "chapter/cover",
            "title",
            ("Second extra note.", "First extra note.", "Second extra note."),
        ),
    ],
)
def test_duplicate_boxes_keep_all_extra_words_and_the_original_edit(tmp_path, section, field, extra_words):
    source = tmp_path / "deck.md"
    source.write_text(
        "---\ndoctype: pitch-deck\nformat: slides\ntitle: Readout\n---\n\n"
        f'::: {{#{section} .section intent="cover"}}\n## Readout\n\n'
        "Original subtitle.\n:::\n",
        encoding="utf-8",
    )
    assert main(["build", str(source)]) == 0
    version = tmp_path / "deck.versions" / "v1"
    deck = Presentation(str(version / "deck.pptx"))
    slide = deck.slides[0]
    original = next(shape for shape in slide.shapes if shape.name == f"{section}/{field}")
    edited_words = "Revised wording in the original box."
    original.text = edited_words
    reviewed = tmp_path / "deck-reviewed.pptx"
    deck.save(str(reviewed))

    # The same edit without duplicates must still map to its named field.
    assert main(["review", "read", str(reviewed)]) == 0
    control = json.loads((version / "review-plan.json").read_text(encoding="utf-8"))
    assert control["sections"][section]["fields"] == {field: edited_words}
    assert control["sections"][section]["owner"] == "human"
    assert control["confirm"] == []

    for text in extra_words:
        duplicate = copy.deepcopy(original._element)
        properties = duplicate.find(".//{http://schemas.openxmlformats.org/presentationml/2006/main}cNvPr")
        assert properties is not None
        properties.set("id", str(max(shape.shape_id for shape in slide.shapes) + 1))
        slide.shapes._spTree.insert_element_before(duplicate, "p:extLst")
        added = next(shape for shape in slide.shapes if shape._element is duplicate)
        added.text = text
    deck.save(str(reviewed))

    assert main(["review", "read", str(reviewed)]) == 0
    plan = json.loads((version / "review-plan.json").read_text(encoding="utf-8"))
    assert plan["sections"][section]["fields"] == {field: edited_words}, (
        f"An added box replaced the original box's wording edit: {plan}"
    )
    assert plan["sections"][section]["owner"] == "human"
    unplaced = [item["text"] for item in plan["confirm"] if item["kind"] == "unplaced"]
    assert len(unplaced) == len(extra_words), f"Each added box needs its own unplaced item: {plan}"
    for text, count in Counter(extra_words).items():
        assert sum(text in item for item in unplaced) == count, f"Added words were lost or repeated: {plan}"
    assert all(item["kind"] == "unplaced" for item in plan["confirm"])
    assert not any(warning["code"] == "tracking_warning" for warning in plan["warnings"])
