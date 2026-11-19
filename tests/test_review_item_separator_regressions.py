"""Command line regressions for head separators and plain bullets in older Word copies."""

import json
from pathlib import Path

import pytest
from docx import Document

from ai_docs_kit.cli import main
from ai_docs_kit.render import word
from ai_docs_kit.source.parser import parse

SOURCE = """---
doctype: report
format: doc
title: Review note
---

## Sources

- [S1] Annual cost ledger

::: {#headed01 .section intent="body"}
## Findings

- **Cost:** Estimate: remains on file [S1 p. 4]
  - Keep the supporting detail
- **Risk:** Evidence remains available

The findings close with a paragraph long enough to give the page ink for the build checks.
:::

::: {#plain01 .section intent="body"}
## Actions

- Keep the original wording [S1 p. 7]
  - Keep the supporting action

The action closes with a paragraph long enough to give the page ink for the build checks.
:::
"""


def _sections(path: Path):
    document, _ = parse(path.read_text(encoding="utf-8"))
    return {section.id: section for section in document.sections}


def _round_trip(tmp_path, capsys, old_text, new_text):
    source = tmp_path / "report.md"
    source.write_text(SOURCE, encoding="utf-8")
    assert main(["build", str(source)]) == 0
    before = _sections(source)
    document = Document(str(tmp_path / "report.versions" / "v1" / "report.docx"))
    paragraph = next(p for p in document.paragraphs if p.text == old_text)
    paragraph.runs[0].text = new_text
    for run in paragraph.runs[1:]:
        run.text = ""
    reviewed = tmp_path / "report-reviewed.docx"
    document.save(str(reviewed))
    capsys.readouterr()
    assert main(["review", "read", str(reviewed)]) == 0
    output = capsys.readouterr().out
    plan_path = Path(next(line.split()[-1] for line in output.splitlines() if line.endswith(".json")))
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert main(["review", "apply", str(source), "--plan", str(plan_path)]) == 0
    return before, _sections(source), plan


@pytest.mark.parametrize("new_head", ["Annual cost", "Cost: annual"])
def test_head_edit_uses_the_unchanged_body_suffix(tmp_path, capsys, new_head):
    before, after, plan = _round_trip(
        tmp_path,
        capsys,
        "Cost: Estimate: remains on file Keep the supporting detail",
        f"{new_head}: Estimate: remains on file Keep the supporting detail",
    )
    assert plan["sections"]["headed01"]["items"][0].startswith(f"{new_head}: Estimate:")
    original = before["headed01"].items[0]
    edited = after["headed01"].items[0]
    assert edited.head == f"{new_head}:"
    assert edited.body == original.body
    assert edited.sub == original.sub
    assert edited.citations == original.citations
    assert after["headed01"].items[1:] == before["headed01"].items[1:]
    assert after["plain01"].items == before["plain01"].items


def test_older_copy_keeps_a_sole_reworded_plain_bullets_citation(tmp_path, capsys, monkeypatch):
    def older_item_text(item):
        text = f"{item['head']}: {item['body']}" if item.get("head") else item["body"]
        return " ".join([text, *item.get("sub", [])])

    # Build the copy as the older writer did, without patching a stored version.
    monkeypatch.setattr(word, "_item_text", older_item_text)
    before, after, plan = _round_trip(
        tmp_path,
        capsys,
        "Keep the original wording Keep the supporting action",
        "Keep the revised wording Keep the supporting action",
    )
    assert plan["sections"]["plain01"]["items"] == ["Keep the revised wording Keep the supporting action"]
    assert plan["sections"]["headed01"].get("items") is None
    original = before["plain01"].items[0]
    edited = after["plain01"].items[0]
    assert edited.head is None
    assert edited.body == "Keep the revised wording"
    assert edited.sub == original.sub
    assert edited.citations == original.citations
    assert after["headed01"].items == before["headed01"].items
