"""Paragraph escapes belong to the working file, never to rendered fields."""

import json
import shutil
from pathlib import Path

from docx import Document as WordDocument

from ai_docs_kit.cli import main
from ai_docs_kit.model import Document, Item, Section
from ai_docs_kit.render.marks import FIELD_PATTERN
from ai_docs_kit.source import serialise


def test_build_keeps_marker_paragraphs_unescaped_in_pdf_fields_and_word(tmp_path, capsys):
    paragraphs = [f"{marker} keep this as prose." for marker in ("-", "*", "+", "1.", "12)")]
    document = Document(
        front={"doctype": "report"},
        format="doc",
        sections=[
            Section(id="prose", intent="body", paragraphs=paragraphs),
            Section(id="list", intent="bullets", items=[Item(body="keep this as a list item.")]),
        ],
    )
    working = tmp_path / "markers.md"
    working.write_text(serialise(document), encoding="utf-8")
    assert main(["build", str(working)]) == 0
    version = Path(capsys.readouterr().out.strip().splitlines()[-1])
    facts = json.loads((version / "layout.json").read_text(encoding="utf-8"))
    fields = [mark["field"] for mark in facts["marks"] if mark.get("field")]
    assert all(FIELD_PATTERN.fullmatch(field) for field in fields)
    assert {f"paragraphs[{index}]" for index in range(len(paragraphs))} <= set(fields)
    pdf_text = " ".join(word["text"] for word in facts["words"] if word["section_id"] == "prose")
    for paragraph in paragraphs:
        assert paragraph in pdf_text
    assert "\\" not in pdf_text
    word_paragraphs = WordDocument(str(version / "markers.docx")).paragraphs
    prose = [paragraph.text for paragraph in word_paragraphs if not paragraph.style.name.startswith("List")]
    assert prose == paragraphs
    assert [p.text for p in word_paragraphs if p.style.name.startswith("List")] == ["keep this as a list item."]
    assert "\\" not in "\n".join(paragraph.text for paragraph in word_paragraphs)
    # Keep the rendered page beside the test's working file for visual inspection.
    shutil.copyfile(version / "pages/p01.png", tmp_path / "paragraph-markers.png")
