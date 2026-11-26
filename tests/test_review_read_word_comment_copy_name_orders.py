"""Comment and section order must not change the Word review copy's filename."""

import json
from pathlib import Path

import pytest
from docx import Document

from ai_docs_kit.cli import main


@pytest.mark.parametrize(
    ("section_order", "comment_order"),
    [(("alpha", "beta"), ("beta", "alpha")), (("beta", "alpha"), ("alpha", "beta"))],
)
def test_comments_preserve_copy_name_in_either_order(
    tmp_path: Path, section_order: tuple[str, str], comment_order: tuple[str, str]
) -> None:
    bodies = {"alpha": "Keep the original wording.", "beta": "Keep the next step."}
    comments = {"alpha": "Please clarify the date.", "beta": "Please explain the next step."}
    source = tmp_path / "note.md"
    source.write_text(
        "---\ndoctype: report\nformat: doc\ntitle: Note\n---\n\n"
        + "\n\n".join(
            f'::: {{#{section_id} .section intent="body"}}\n## The direction\n\n{bodies[section_id]}\n:::'
            for section_id in section_order
        )
        + "\n",
        encoding="utf-8",
    )
    original_source = source.read_bytes()
    assert main(["build", str(source)]) == 0
    version = tmp_path / "note.versions" / "v1"
    original_copy = (version / "note.docx").read_bytes()
    copy = tmp_path / "note-reviewed-round-2.docx"
    copy.write_bytes(original_copy)
    assert main(["review", "read", str(copy)]) == 0
    plan_path = version / "review-plan.json"
    control = json.loads(plan_path.read_bytes())
    assert control["review_copy"] == copy.name
    assert all(not section["confirm"] for section in control["sections"].values())

    document = Document(copy)
    for section_id in comment_order:
        paragraph = next(p for p in document.paragraphs if p.text == bodies[section_id])
        document.add_comment(paragraph.runs, comments[section_id], author="Reviewer")
    document.save(copy)
    commented_copy = copy.read_bytes()
    assert main(["review", "read", str(copy)]) == 0
    reviewed = json.loads(plan_path.read_bytes())
    for section_id in section_order:
        section = reviewed["sections"][section_id]
        assert len(section["confirm"]) == 1
        assert section["confirm"][0]["text"] == comments[section_id]
        assert section["confirm"][0]["anchor"] == bodies[section_id]
        assert section["wording"] is None
    assert source.read_bytes() == original_source
    assert copy.read_bytes() == commented_copy
    assert (version / "note.docx").read_bytes() == original_copy
    assert reviewed["review_copy"] == copy.name
