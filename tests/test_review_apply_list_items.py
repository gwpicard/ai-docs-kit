"""`review read` and `review apply` carry a reviewer's bullet edits from the Word copy to the working file.

Plan shape these tests pin: `sections[<id>].items` is the section's list items from the Word copy, in
order, as plain strings; it is absent or null when the list is unchanged.
"""

import copy
import json
import shutil
from pathlib import Path

import pytest
from docx import Document

from ai_docs_kit.cli import main
from ai_docs_kit.source.parser import parse

SOURCE = """---
doctype: report
format: doc
title: Note
---

::: {#alpha01 .section intent="body"}
## Alpha

Alpha keeps its original wording here.
:::

::: {#list01 .section intent="body"}
## Findings

- First finding stands here
- Second finding stands here
- Third finding stands here

The findings close with this paragraph.
:::

::: {#list02 .section intent="body"}
## Actions

- Ship the draft
- Review the draft
:::
"""

SENT_FINDINGS = ["First finding stands here", "Second finding stands here", "Third finding stands here"]


@pytest.fixture(scope="module")
def sent(tmp_path_factory) -> Path:
    folder = tmp_path_factory.mktemp("sent")
    (folder / "report.md").write_text(SOURCE, encoding="utf-8")
    assert main(["build", str(folder / "report.md")]) == 0
    version = folder / "report.versions" / "v1"
    empty = folder / "none.json"
    empty.write_text("[]")
    assert main(["look", str(version), "--findings", str(empty)]) == 0
    assert main(["sent", str(version), "--to", "Reviewer"]) == 0
    return folder


@pytest.fixture
def work(sent, tmp_path) -> Path:
    shutil.copytree(sent, tmp_path / "w")
    return tmp_path / "w"


def _bullet(document, text: str):
    return next(p for p in document.paragraphs if p.text == text)


def _read(work: Path, capsys, edit) -> dict:
    """The plan `review read` writes for the sent Word copy after `edit(document)`."""
    target = work / "report-reviewed.docx"
    document = Document(str(work / "report.versions" / "v1" / "report.docx"))
    edit(document)
    document.save(str(target))
    assert main(["review", "read", str(target)]) == 0
    out = capsys.readouterr().out
    paths = [Path(line.split()[-1]) for line in out.splitlines() if line.strip().endswith(".json")]
    return json.loads(paths[-1].read_text(encoding="utf-8"))


def _apply(work: Path, plan: dict, tmp_path: Path, capsys) -> None:
    decided = tmp_path / "decided.json"
    decided.write_text(json.dumps(plan), encoding="utf-8")
    code = main(["review", "apply", str(work / "report.md"), "--plan", str(decided)])
    assert code == 0, capsys.readouterr().err


def _section(work: Path, section_id: str):
    doc, _ = parse((work / "report.md").read_text(encoding="utf-8"))
    return next(s for s in doc.sections if s.id == section_id)


def _bodies(section) -> list[str]:
    return [item.body for item in section.items]


def _edit_add_delete(document) -> None:
    _bullet(document, "First finding stands here").runs[0].text = "First finding was reworded"
    second = _bullet(document, "Second finding stands here")
    second._p.getparent().remove(second._p)
    third = _bullet(document, "Third finding stands here")
    added = copy.deepcopy(third._p)
    third._p.addnext(added)
    new = next(p for p in document.paragraphs if p._p is added)
    new.runs[0].text = "A fourth finding was added"
    for run in new.runs[1:]:
        run.text = ""


EDITED = ["First finding was reworded", "Third finding stands here", "A fourth finding was added"]


def test_read_records_the_edited_list_in_order(work, capsys):
    plan = _read(work, capsys, _edit_add_delete)
    assert plan["sections"]["list01"]["items"] == EDITED


def test_read_records_nothing_for_a_list_left_alone(work, capsys):
    plan = _read(work, capsys, _edit_add_delete)
    assert plan["sections"]["list02"].get("items") is None
    assert plan["sections"]["alpha01"].get("items") is None


def test_read_records_a_single_edited_bullet_of_another_section(work, capsys):
    def edit(document):
        _bullet(document, "Review the draft").runs[0].text = "Approve the draft"

    plan = _read(work, capsys, edit)
    assert plan["sections"]["list02"]["items"] == ["Ship the draft", "Approve the draft"]
    assert plan["sections"]["list01"].get("items") is None


def test_apply_sets_edited_added_and_removed_bullets_and_marks_human(work, tmp_path, capsys):
    plan = _read(work, capsys, _edit_add_delete)
    _apply(work, plan, tmp_path, capsys)
    section = _section(work, "list01")
    assert _bodies(section) == EDITED
    assert section.owner == "human"
    assert _section(work, "alpha01").owner is None


def test_apply_gives_both_changed_paragraphs_and_items(work, tmp_path, capsys):
    def edit(document):
        _edit_add_delete(document)
        paragraph = _bullet(document, "The findings close with this paragraph.")
        paragraph.runs[0].text = "The findings close with a revised paragraph."
        for run in paragraph.runs[1:]:
            run.text = ""

    plan = _read(work, capsys, edit)
    _apply(work, plan, tmp_path, capsys)
    section = _section(work, "list01")
    assert _bodies(section) == EDITED
    assert "The findings close with a revised paragraph." in section.paragraphs
    assert "The findings close with this paragraph." not in section.paragraphs
    assert not [p for p in section.paragraphs if "finding" in p and "close" not in p]
    assert section.owner == "human"


def test_apply_keeps_the_items_of_a_section_whose_paragraphs_alone_changed(work, tmp_path, capsys):
    def edit(document):
        paragraph = _bullet(document, "The findings close with this paragraph.")
        paragraph.runs[0].text = "The findings close with a new paragraph."
        for run in paragraph.runs[1:]:
            run.text = ""

    plan = _read(work, capsys, edit)
    _apply(work, plan, tmp_path, capsys)
    section = _section(work, "list01")
    assert _bodies(section) == SENT_FINDINGS
    assert "The findings close with a new paragraph." in section.paragraphs
    assert not [p for p in section.paragraphs if "finding" in p and "close" not in p]


def test_apply_keeps_an_unchanged_list_exactly(work, tmp_path, capsys):
    before = _section(work, "list02")
    plan = _read(work, capsys, _edit_add_delete)
    _apply(work, plan, tmp_path, capsys)
    after = _section(work, "list02")
    assert after.items == before.items
    assert after.owner is None


def test_the_schema_describes_items():
    schema = Path(__file__).resolve().parents[1] / "docs" / "schemas" / "review" / "ReviewPlan.schema.json"
    section = json.loads(schema.read_text(encoding="utf-8"))["$defs"]["SectionPlan"]
    assert "items" in section["properties"]
