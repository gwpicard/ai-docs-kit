"""Issue 375 review: table figures and multiline human wording survive builds."""

import json

import pytest
from docx import Document as WordDocument

from ai_docs_kit import api


def _write(tmp_path, format_, intent):
    path = tmp_path / "readings.md"
    path.write_text(
        f"---\nformat: {format_}\n---\n\n"
        "## Sources\n\n- [S1] The reading is 12.\n\n"
        f'::: {{#reading .section intent="{intent}"}}\n## Readings\n\nOriginal words.\n:::\n',
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize("kind", ["number", "text-cell", "column-heading"])
def test_human_table_cells_have_supported_and_unsupported_builds(tmp_path, kind):
    path = _write(tmp_path, "slides", "table")
    for revision, number in enumerate((12, 987)):
        value = str(number) if kind == "text-cell" else number
        data = {"columns": ["Metric", "Value"], "rows": [["Reading", value]]}
        field = "data.rows[0][1]"
        if kind == "column-heading":
            data = {"columns": ["Metric", str(number)], "rows": [["Reading", 12]]}
            field = "data.columns[1]"
        edit = api.edit_fields(path, "reading", {"data": data}, revision)
        assert edit.section.owner == "human" and edit.section.data == data
        saved = path.read_bytes()
        built = api.build(path)
        assert path.read_bytes() == saved
        composition = json.loads((built.version / "composition.json").read_bytes())
        assert composition["sections"][0]["content"]["data"] == data
        findings = [finding for finding in built.findings if finding.rule_id == "source.number-in-source"]
        measured = [(f.section_id, f.measured["number"], f.measured["field"]) for f in findings]
        assert measured == ([] if number == 12 else [("reading", "987", field)])
        layout = json.loads((built.version / "layout.json").read_bytes())
        assert str(number) in {word["text"] for word in layout["words"] if word["section_id"] == "reading"}


def test_multiline_human_paragraphs_survive_edit_read_build_and_repeated_saves(tmp_path):
    path = _write(tmp_path, "doc", "body")
    paragraphs = [
        "Ordinary prose stays a separate paragraph.",
        "First line\n- the person's next line",
        "Another first line\n* asterisk text\n+ plus text\n12) numbered text",
        "Keep blank lines\n\n  and indentation.\n",
        "Keep a closing fence\n:::\nand a code fence\n```\ninside this paragraph.",
        "Keep a note as text\n> note: the person's words\n## Keep a heading as text",
        "Keep café, £ and \\q.\r\n- Keep the carriage return too.",
    ]
    for revision in range(2):
        edit = api.edit_fields(path, "reading", {"paragraphs": paragraphs}, revision)
        assert edit.section.paragraphs == paragraphs
        section = api.read_document(path).sections[0]
        assert section.paragraphs == paragraphs
        assert section.items == [] and section.code == [] and section.note is None
        assert section.title == "Readings" and section.data is None
    saved = path.read_bytes()
    built = api.build(path)
    assert path.read_bytes() == saved
    composition = json.loads((built.version / "composition.json").read_bytes())
    assert [p.encode("utf-8") for p in composition["sections"][0]["props"]["paragraphs"]] == [
        p.encode("utf-8") for p in paragraphs
    ]
    layout = json.loads((built.version / "layout.json").read_bytes())
    text = " ".join(word["text"] for word in layout["words"] if word["section_id"] == "reading")
    assert "- the person's next line" in text
    assert "and indentation." in text and "the person's words" in text
    word = WordDocument(str(built.version / "readings.docx"))
    wording = [paragraph.text for paragraph in word.paragraphs if not paragraph.style.name.startswith("Heading")]
    assert wording[:-1] == paragraphs[:-1]
    assert wording[-1].split() == paragraphs[-1].split()
