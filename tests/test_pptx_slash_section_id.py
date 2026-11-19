"""A section id with a slash comes back from the PowerPoint copy as that id, not cut at the slash."""

import json
import zipfile

from ai_docs_kit.cli import main

DECK = """---
doctype: pitch-deck
format: slides
title: Readout
---

::: {#cover intent=cover}
## Readout
A short deck.
:::

::: {#a/b intent=statement}
## A clear direction
Simple ideas make a strong story.
:::
"""


def test_review_read_keeps_a_slash_in_the_section_id(tmp_path, capsys):
    (tmp_path / "deck.md").write_text(DECK, encoding="utf-8")
    assert main(["build", str(tmp_path / "deck.md")]) == 0
    version = tmp_path / "deck.versions" / "v1"
    empty = tmp_path / "none.json"
    empty.write_text("[]")
    assert main(["look", str(version), "--findings", str(empty)]) == 0
    with zipfile.ZipFile(version / "deck.pptx") as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    for name in parts:
        if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
            parts[name] = parts[name].replace(b"Simple ideas make", b"Simple notions make")
    copy = tmp_path / "reviewed.pptx"
    with zipfile.ZipFile(copy, "w") as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    capsys.readouterr()
    assert main(["review", "read", str(copy)]) == 0
    plan = json.loads((version / "review-plan.json").read_text(encoding="utf-8"))
    assert "a/b" in plan["sections"], list(plan["sections"])
    assert "a" not in plan["sections"]
