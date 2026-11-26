"""Adding a Word comment must not replace the recorded review copy's name with a section id."""

import json
from pathlib import Path

from docx import Document

from ai_docs_kit.cli import main


def test_word_comment_preserves_review_copy_name(tmp_path: Path) -> None:
    source = tmp_path / "note.md"
    source.write_text(
        "---\ndoctype: report\nformat: doc\ntitle: Note\n---\n\n"
        '::: {#alpha .section intent="body"}\n## The direction\n\n'
        "Keep the original wording.\n:::\n",
        encoding="utf-8",
    )
    assert main(["build", str(source)]) == 0
    version = tmp_path / "note.versions" / "v1"
    copy = tmp_path / "note-reviewed.docx"
    copy.write_bytes((version / "note.docx").read_bytes())
    assert main(["review", "read", str(copy)]) == 0
    plan = version / "review-plan.json"
    assert json.loads(plan.read_bytes())["review_copy"] == copy.name

    document = Document(copy)
    paragraph = next(p for p in document.paragraphs if p.text == "Keep the original wording.")
    document.add_comment(paragraph.runs, "Please clarify the date.", author="Reviewer")
    document.save(copy)
    assert main(["review", "read", str(copy)]) == 0
    reviewed = json.loads(plan.read_bytes())
    assert reviewed["sections"]["alpha"]["confirm"][0]["text"] == "Please clarify the date."
    assert reviewed["review_copy"] == copy.name, f"A comment changed the recorded copy name: {reviewed}"
