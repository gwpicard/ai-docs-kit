"""Word review keeps an unchanged trailing source apart from body wording."""

import json

import pytest
from docx import Document

from ai_docs_kit.cli import main
from ai_docs_kit.source.parser import parse

REFERENCE = "Illustrative research notes"
ORIGINAL = "The original paragraph gives the reader the context."
REVISED = "The revised paragraph gives the reader the context."


@pytest.mark.parametrize(
    ("before", "after", "source_line"),
    [
        ([REFERENCE, ORIGINAL, REFERENCE], [REFERENCE, REVISED, REFERENCE], REFERENCE),
        ([ORIGINAL], [], REFERENCE),
        ([ORIGINAL], [ORIGINAL], REFERENCE),
        ([ORIGINAL, REFERENCE], [REVISED, REFERENCE], ""),
        ([ORIGINAL], [REVISED], "Illustrative   research notes"),
    ],
    ids=["repeated-body-text", "cleared-body", "unchanged-copy", "no-source", "source-spacing"],
)
def test_review_plan_and_apply_keep_body_boundaries(tmp_path, before, after, source_line):
    source = tmp_path / "report.md"
    body = "\n\n".join(before)
    citation = f"\n\n> source: {source_line}" if source_line else ""
    source.write_text(
        "---\ndoctype: report\nformat: doc\ntitle: Readout\n---\n\n"
        f'::: {{#opening .section intent="body"}}\n## Opening\n\n{body}{citation}\n:::\n',
        encoding="utf-8",
    )
    assert main(["build", str(source)]) == 0
    version = tmp_path / "report.versions" / "v1"
    document = Document(str(version / "report.docx"))
    body_paragraphs = document.paragraphs[1 : 1 + len(before)]
    for paragraph, text in zip(body_paragraphs, after, strict=False):
        paragraph.runs[0].text = text
    for paragraph in body_paragraphs[len(after) :]:
        paragraph._p.getparent().remove(paragraph._p)
    reviewed = tmp_path / "report-reviewed.docx"
    document.save(str(reviewed))

    assert main(["review", "read", str(reviewed)]) == 0
    plan_path = version / "review-plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    section = plan["sections"]["opening"]
    assert section["wording"] == ("\n\n".join(after) if before != after else None)
    assert section["owner"] == ("human" if before != after else None)
    assert not plan["confirm"]
    assert main(["review", "apply", str(source), "--plan", str(plan_path)]) == 0
    result, _ = parse(source.read_text(encoding="utf-8"))
    assert result.sections[0].paragraphs == after
    assert result.sections[0].source_line == (source_line or None)
