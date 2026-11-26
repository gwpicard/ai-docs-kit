"""A slide with notes and no visible text still carries its section through review."""

import json

from PIL import Image
from pptx import Presentation

from ai_docs_kit.cli import main

R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def test_deleting_a_textless_slide_reports_its_section(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    Image.new("RGB", (960, 540), "#406080").save(assets / "illustration.png")
    source = tmp_path / "deck.md"
    source.write_text(
        "---\ndoctype: pitch-deck\nformat: slides\ntitle: Readout\n---\n\n"
        '::: {#opening .section intent="cover"}\n## Readout\n\nA short readout.\n:::\n\n'
        '::: {#pause .section intent="full-image" image="illustration.png"}\n'
        "> note: Pause for questions.\n:::\n\n"
        '::: {#closing .section intent="closing"}\n## Thank you\n:::\n',
        encoding="utf-8",
    )
    assert main(["build", str(source)]) == 0
    version = tmp_path / "deck.versions" / "v1"
    deck = Presentation(str(version / "deck.pptx"))
    assert len(deck.slides) == 3
    assert deck.slides[1].notes_slide.notes_text_frame.text == "Pause for questions."
    assert not any(s.text.strip() for s in deck.slides[1].shapes if s.has_text_frame)
    reviewed = tmp_path / "deck-reviewed.pptx"
    deck.save(str(reviewed))
    assert main(["review", "read", str(reviewed)]) == 0
    plan_path = version / "review-plan.json"
    control = json.loads(plan_path.read_text(encoding="utf-8"))
    assert control["confirm"] == []

    slides = deck.slides._sldIdLst
    removed = slides[1]
    deck.part.drop_rel(removed.get(f"{{{R}}}id"))
    slides.remove(removed)
    deck.save(str(reviewed))
    assert main(["review", "read", str(reviewed)]) == 0
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    deleted = [item["section"] for item in plan["confirm"] if item["kind"] == "delete"]
    assert deleted == ["pause"], f"The textless section disappeared without a deletion item: {plan}"
