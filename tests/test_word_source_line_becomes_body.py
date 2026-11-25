"""Editing Word body text must not copy an unchanged source line into the body."""

from docx import Document

from ai_docs_kit.cli import main
from ai_docs_kit.source.parser import parse


def test_body_edit_does_not_duplicate_the_source_line(tmp_path):
    source = tmp_path / "report.md"
    source.write_text(
        "---\ndoctype: report\nformat: doc\ntitle: Readout\n---\n\n"
        '::: {#opening .section intent="body"}\n## Opening\n\n'
        "The original paragraph gives the reader the context.\n\n"
        "> source: Illustrative research notes\n:::\n",
        encoding="utf-8",
    )
    assert main(["build", str(source)]) == 0
    version = tmp_path / "report.versions" / "v1"
    document = Document(str(version / "report.docx"))
    paragraph = next(p for p in document.paragraphs if p.text.startswith("The original paragraph"))
    paragraph.runs[0].text = "The revised paragraph gives the reader the context."
    assert any(p.text == "Illustrative research notes" for p in document.paragraphs)
    reviewed = tmp_path / "report-reviewed.docx"
    document.save(str(reviewed))

    assert main(["review", "read", str(reviewed)]) == 0
    assert main(["review", "apply", str(source), "--plan", str(version / "review-plan.json")]) == 0
    after, _ = parse(source.read_text(encoding="utf-8"))
    assert after.sections[0].source_line == "Illustrative research notes"
    assert after.sections[0].paragraphs == ["The revised paragraph gives the reader the context."], (
        "The unchanged source line was applied as an extra body paragraph"
    )
