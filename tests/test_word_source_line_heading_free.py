"""Clearing a heading-free Word body keeps a section whose source remains."""

import json

import pytest
from docx import Document

from ai_docs_kit.cli import main
from ai_docs_kit.source.parser import parse

REFERENCE = "Illustrative research notes"


@pytest.mark.parametrize("remove_section", [False, True], ids=["clear-body-runs", "delete-section"])
@pytest.mark.parametrize("with_list", [False, True], ids=["paragraph", "paragraph-and-list"])
def test_heading_free_body_clear_keeps_source_and_section(tmp_path, remove_section, with_list):
    source = tmp_path / "report.md"
    bullet = "- A supporting point.\n\n" if with_list else ""
    source.write_text(
        "---\ndoctype: report\nformat: doc\ntitle: Readout\n---\n\n"
        '::: {#opening .section intent="body"}\n'
        "The original paragraph gives the reader the context.\n\n"
        f"{bullet}> source: {REFERENCE}\n:::\n",
        encoding="utf-8",
    )
    assert main(["build", str(source)]) == 0
    version = tmp_path / "report.versions" / "v1"
    document = Document(str(version / "report.docx"))
    expected = ["The original paragraph gives the reader the context."]
    if with_list:
        expected.append("A supporting point.")
    assert [paragraph.text for paragraph in document.paragraphs] == [*expected, REFERENCE]
    if remove_section:
        for paragraph in document.paragraphs:
            paragraph._p.getparent().remove(paragraph._p)
    else:
        for paragraph in document.paragraphs[:-1]:
            for run in paragraph.runs:
                run.text = ""
    reviewed = tmp_path / "report-reviewed.docx"
    document.save(str(reviewed))

    assert main(["review", "read", str(reviewed)]) == 0
    plan_path = version / "review-plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    section = plan["sections"]["opening"]
    if remove_section:
        assert section["wording"] is None
        assert [(item["kind"], item["section"]) for item in plan["confirm"]] == [("delete", "opening")]
        plan["confirm"][0].update(accepted=True, action="restructure")
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
    else:
        assert section["wording"] == ""
        assert section["owner"] == "human"
        assert section["items"] == ([] if with_list else None)
        assert not plan["confirm"]
    assert main(["review", "apply", str(source), "--plan", str(plan_path)]) == 0
    result, _ = parse(source.read_text(encoding="utf-8"))
    if remove_section:
        assert not result.sections
    else:
        assert len(result.sections) == 1
        assert result.sections[0].id == "opening"
        assert result.sections[0].title is None
        assert result.sections[0].paragraphs == []
        assert result.sections[0].items == []
        assert result.sections[0].source_line == REFERENCE
        assert result.sections[0].owner == "human"
