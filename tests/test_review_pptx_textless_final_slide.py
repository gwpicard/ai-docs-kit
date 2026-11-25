"""Review identifies a deleted image-only section at the end of a deck."""

import json

from PIL import Image
from pptx import Presentation

from ai_docs_kit.cli import main

R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def test_deleting_final_textless_slide_reports_only_its_section(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    Image.new("RGB", (960, 540), "#608040").save(assets / "illustration.png")
    source = tmp_path / "deck.md"
    source.write_text(
        "---\ndoctype: pitch-deck\nformat: slides\ntitle: Readout\n---\n\n"
        '::: {#zulu .section intent="cover"}\n## Readout\n\nA short readout.\n:::\n\n'
        '::: {#middle .section intent="closing"}\n## Thank you\n:::\n\n'
        '::: {#alpha .section intent="full-image" image="illustration.png"}\n'
        "> note: Pause for questions.\n:::\n",
        encoding="utf-8",
    )
    original_source = source.read_bytes()
    assert main(["build", str(source)]) == 0
    version = tmp_path / "deck.versions" / "v1"
    original_copy = (version / "deck.pptx").read_bytes()
    deck = Presentation(str(version / "deck.pptx"))
    assert len(deck.slides) == 3
    final_slide = deck.slides[2]
    assert any(shape.shape_type == 13 for shape in final_slide.shapes)
    assert not any(shape.text.strip() for shape in final_slide.shapes if shape.has_text_frame)
    assert final_slide.notes_slide.notes_text_frame.text == "Pause for questions."

    reviewed = tmp_path / "deck-reviewed.pptx"
    deck.save(str(reviewed))
    assert main(["review", "read", str(reviewed)]) == 0
    plan_path = version / "review-plan.json"
    control = json.loads(plan_path.read_text(encoding="utf-8"))
    assert control["confirm"] == []

    slides = deck.slides._sldIdLst
    removed = slides[2]
    deck.part.drop_rel(removed.get(f"{{{R}}}id"))
    slides.remove(removed)
    deck.save(str(reviewed))
    assert len(Presentation(str(reviewed)).slides) == 2
    assert main(["review", "read", str(reviewed)]) == 0
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert [(item["kind"], item.get("section")) for item in plan["confirm"]] == [("delete", "alpha")], plan
    assert not any(warning["code"] == "tracking_warning" for warning in plan["warnings"]), plan
    assert source.read_bytes() == original_source
    assert (version / "deck.pptx").read_bytes() == original_copy
