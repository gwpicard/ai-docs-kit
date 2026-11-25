"""Word comments must be read from their relationship target, even when the part has another name."""

import json
import zipfile
from pathlib import Path

from docx import Document
from lxml import etree

from ai_docs_kit.cli import main

R = "http://schemas.openxmlformats.org/package/2006/relationships"


def test_review_read_keeps_comments_in_a_renamed_word_part(tmp_path: Path) -> None:
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
    document = Document(version / "note.docx")
    paragraph = next(p for p in document.paragraphs if p.text == "Keep the original wording.")
    text = "Please clarify the date."
    document.add_comment(paragraph.runs, text, author="Reviewer")
    document.save(copy)
    assert main(["review", "read", str(copy)]) == 0
    plan = version / "review-plan.json"
    control = json.loads(plan.read_bytes())
    assert [item["text"] for item in control["sections"]["alpha"]["confirm"]] == [text]

    with zipfile.ZipFile(copy) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    original_name = "word/comments.xml"
    renamed = "word/reviewer-comments.xml"
    parts[renamed] = parts.pop(original_name)
    rels = etree.fromstring(parts["word/_rels/document.xml.rels"])
    comment_rels = [rel for rel in rels.findall(f"{{{R}}}Relationship") if rel.get("Type", "").endswith("/comments")]
    assert len(comment_rels) == 1
    assert comment_rels[0].get("Target") == "comments.xml"
    comment_rels[0].set("Target", "reviewer-comments.xml")
    parts["word/_rels/document.xml.rels"] = etree.tostring(rels)
    parts["[Content_Types].xml"] = parts["[Content_Types].xml"].replace(
        b"/word/comments.xml", b"/word/reviewer-comments.xml"
    )
    with zipfile.ZipFile(copy, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)

    # The Office package library still finds the same anchored comment in the renamed part.
    assert [(comment.author, comment.text) for comment in Document(copy).comments] == [("Reviewer", text)]
    assert main(["review", "read", str(copy)]) == 0
    reviewed = json.loads(plan.read_bytes())
    assert [item["text"] for item in reviewed["sections"]["alpha"]["confirm"]] == [text], (
        f"The review reader lost a comment after its valid relationship target was renamed: {reviewed}"
    )
