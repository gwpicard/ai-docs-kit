"""`review read` keeps a section's heading (`title`) apart from its body (`wording`); `review apply` uses both."""

import json
import shutil
from pathlib import Path

from docx import Document

from ai_docs_kit.cli import main
from ai_docs_kit.source.parser import parse

SCHEMA = Path(__file__).resolve().parents[1] / "docs" / "schemas" / "review" / "ReviewPlan.schema.json"

SOURCE = """---
doctype: report
format: doc
title: Note
---

::: {#alpha01 .section intent="body"}
## Alpha

Alpha keeps its original wording here.
:::

::: {#beta01 .section intent="body"}
## Beta

Beta

Beta holds a second line for the note.
:::
"""


def _sent(tmp_path: Path) -> Path:
    (tmp_path / "report.md").write_text(SOURCE, encoding="utf-8")
    assert main(["build", str(tmp_path / "report.md")]) == 0
    v1 = tmp_path / "report.versions" / "v1"
    empty = tmp_path / "none.json"
    empty.write_text("[]")
    assert main(["look", str(v1), "--findings", str(empty)]) == 0
    return v1


def _plan(tmp_path: Path, capsys, edits=(), heading_edits=()) -> dict:
    v1 = _sent(tmp_path)
    copy = tmp_path / "report-reviewed.docx"
    shutil.copyfile(v1 / "report.docx", copy)
    document = Document(str(copy))
    for paragraph in document.paragraphs:
        heading = paragraph.style.name.startswith("Heading")
        for old, new in heading_edits if heading else edits:
            for run in paragraph.runs:
                if old in run.text:
                    run.text = run.text.replace(old, new)
    document.save(str(copy))
    assert main(["review", "read", str(copy)]) == 0
    capsys.readouterr()
    return json.loads((v1 / "review-plan.json").read_text(encoding="utf-8"))


def _apply(tmp_path: Path, plan: dict, capsys) -> dict:
    decided = tmp_path / "decided.json"
    decided.write_text(json.dumps(plan))
    assert main(["review", "apply", str(tmp_path / "report.md"), "--plan", str(decided)]) == 0
    capsys.readouterr()
    doc, _ = parse((tmp_path / "report.md").read_text(encoding="utf-8"))
    return {s.id: s for s in doc.sections}


def test_the_schema_describes_a_section_title():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert "title" in schema["$defs"]["SectionPlan"]["properties"]


def test_a_body_edit_gives_wording_without_the_heading(tmp_path, capsys):
    plan = _plan(tmp_path, capsys, edits=[("original wording", "revised wording")])
    alpha = plan["sections"]["alpha01"]
    assert alpha["wording"] == "Alpha keeps its revised wording here."
    assert alpha.get("title") is None


def test_an_edited_heading_gives_title_and_no_wording(tmp_path, capsys):
    plan = _plan(tmp_path, capsys, heading_edits=[("Alpha", "Alpha Prime")])
    alpha = plan["sections"]["alpha01"]
    assert alpha["title"] == "Alpha Prime"
    assert alpha.get("wording") is None


def test_an_edited_heading_and_body_are_kept_apart(tmp_path, capsys):
    plan = _plan(
        tmp_path, capsys, edits=[("original wording", "revised wording")], heading_edits=[("Alpha", "Alpha Prime")]
    )
    alpha = plan["sections"]["alpha01"]
    assert alpha["title"] == "Alpha Prime"
    assert alpha["wording"] == "Alpha keeps its revised wording here."


def test_an_edited_heading_is_applied_as_the_title_and_not_in_the_body(tmp_path, capsys):
    plan = _plan(
        tmp_path, capsys, edits=[("original wording", "revised wording")], heading_edits=[("Alpha", "Alpha Prime")]
    )
    alpha = _apply(tmp_path, plan, capsys)["alpha01"]
    assert alpha.title == "Alpha Prime"
    assert alpha.paragraphs == ["Alpha keeps its revised wording here."]


def test_an_edited_heading_alone_is_applied_and_keeps_the_body(tmp_path, capsys):
    plan = _plan(tmp_path, capsys, heading_edits=[("Alpha", "Alpha Prime")])
    alpha = _apply(tmp_path, plan, capsys)["alpha01"]
    assert alpha.title == "Alpha Prime"
    assert alpha.paragraphs == ["Alpha keeps its original wording here."]


def test_a_first_paragraph_that_repeats_the_title_is_kept(tmp_path, capsys):
    plan = _plan(tmp_path, capsys, edits=[("second line", "closing line")])
    beta = plan["sections"]["beta01"]
    assert beta["wording"].startswith("Beta\n\n")
    assert beta.get("title") is None
    section = _apply(tmp_path, plan, capsys)["beta01"]
    assert section.title == "Beta"
    assert section.paragraphs == ["Beta", "Beta holds a closing line for the note."]


def test_a_plan_with_a_title_keeps_a_body_paragraph_equal_to_the_old_title(tmp_path, capsys):
    plan = _plan(tmp_path, capsys, edits=[("second line", "closing line")])
    plan["sections"]["beta01"]["title"] = "Beta Two"
    section = _apply(tmp_path, plan, capsys)["beta01"]
    assert section.title == "Beta Two"
    assert section.paragraphs[0] == "Beta"
    assert "Beta Two" not in section.paragraphs


def test_a_plan_written_before_the_split_still_applies(tmp_path, capsys):
    plan = _plan(tmp_path, capsys)
    plan["sections"]["alpha01"]["wording"] = "Alpha\n\nAlpha keeps its revised wording here."
    plan["sections"]["alpha01"].pop("title", None)
    alpha = _apply(tmp_path, plan, capsys)["alpha01"]
    assert alpha.title == "Alpha"
    assert alpha.paragraphs == ["Alpha keeps its revised wording here."]
