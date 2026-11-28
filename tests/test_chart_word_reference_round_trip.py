"""Generated chart references must not become prose during a Word review round trip."""

import json
import shutil
from pathlib import Path

import pytest
from docx import Document as WordDocument
from docx.oxml.ns import qn

from ai_docs_kit.cli import main
from ai_docs_kit.source import parse

DATA = """```data
type: pie
category_label: District
categories: [Upland, Lowland]
series:
  - name: Completed
    values: [17, 29]
```
"""
REFERENCE = "[Chart 1: Survey]"


def _build(working, capsys):
    assert main(["build", str(working)]) == 0
    version = Path(capsys.readouterr().out.strip().splitlines()[-1])
    return version, json.loads((version / "layout.json").read_text(encoding="utf-8"))


def _read(copy, version, capsys):
    assert main(["review", "read", str(copy)]) == 0
    capsys.readouterr()
    path = version / "review-plan.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("data_slot", [0, 1, 2], ids=["data-first", "data-between", "data-last"])
@pytest.mark.parametrize("legacy", [False, True], ids=["marked-reference", "older-copy"])
def test_chart_review_keeps_generated_reference_out_of_prose_and_retains_data_position(
    tmp_path, capsys, data_slot, legacy
):
    original = ["Opening prose survives.", "Closing prose survives."]
    blocks = list(original)
    blocks.insert(data_slot, DATA)
    working = tmp_path / "report.md"
    working.write_text(
        '---\ndoctype: report\nformat: doc\n---\n\n::: {#chart .section intent="chart"}\n## Survey\n\n'
        + "\n\n".join(blocks)
        + '\n\n> source: Closing prose survives.\n:::\n\n::: {#plain .section intent="body"}\n## Literal reference\n\n'
        + REFERENCE
        + "\n:::\n",
        encoding="utf-8",
    )
    version, _ = _build(working, capsys)
    sent = version / "report.docx"
    if legacy:
        document = WordDocument(str(sent))
        for paragraph in document.paragraphs:
            if paragraph.text == REFERENCE:
                paragraph.style = "Normal"
        document.save(str(sent))
    copy = tmp_path / "report-reviewed.docx"
    shutil.copyfile(sent, copy)
    plan_path, intact = _read(copy, version, capsys)
    assert intact["sections"]["chart"]["wording"] is None
    assert intact["sections"]["plain"]["wording"] is None
    assert intact["confirm"] == []
    assert any(w["code"] == "tracking_warning" for w in intact["warnings"])

    document = WordDocument(str(copy))
    for paragraph in document.paragraphs:
        if paragraph.text == original[0]:
            paragraph.runs[0].text = "Opening wording revised."
            for run in paragraph.runs[1:]:
                run.text = ""
    document.save(str(copy))
    plan_path, plan = _read(copy, version, capsys)
    expected = ["Opening wording revised.", original[1]]
    # Continue through apply/build even on the defective reader to check the real PDF.
    assert main(["review", "apply", str(working), "--plan", str(plan_path)]) == 0
    capsys.readouterr()
    rebuilt, facts = _build(working, capsys)
    words = [word for word in facts["words"] if word["section_id"] == "chart"]
    pdf_text = " ".join(word["text"] for word in words)
    assert REFERENCE not in pdf_text, "The generated Word reference leaked into the PDF as prose"
    assert plan["sections"]["chart"]["wording"].split("\n\n") == expected
    assert plan["sections"]["plain"]["wording"] is None
    section = parse(working.read_text(encoding="utf-8"))[0].sections[0]
    assert section.paragraphs == expected
    assert section.data["series"][0]["values"] == [17, 29]
    fields = [f"paragraphs[{i}]" for i in range(2)]
    fields.insert(data_slot, "data")
    assert section.ordered_content() == fields
    positions = []
    for field in fields:
        role = "table-cell" if field == "data" else "paragraph"
        text = "Upland" if field == "data" else expected[int(field[11:-1])]
        visible = [word for word in words if word["role"] == role]
        assert text in " ".join(word["text"] for word in visible)
        marks = [mark for mark in facts["marks"] if mark.get("field") == field and mark["id"] == "chart"]
        if field == "data":
            marks = [mark for mark in facts["marks"] if mark.get("field") == "data.categories[0]"]
        assert marks
        positions.append(min((mark["page"], mark["y"]) for mark in marks))
    assert positions == sorted(positions)
    word_lines = [paragraph.text for paragraph in WordDocument(str(rebuilt / "report.docx")).paragraphs]
    expected_lines = list(expected)
    expected_lines.insert(data_slot, REFERENCE)
    assert word_lines[:3] == expected_lines
    assert word_lines.count(REFERENCE) == 2, "Keep the literal reference in the separate body section"


@pytest.mark.parametrize("change", ["insert-before", "delete-before", "split-before", "move-reference"])
def test_chart_review_preserves_data_position_when_paragraph_counts_or_reference_position_change(
    tmp_path, capsys, change
):
    working = tmp_path / "report.md"
    working.write_text(
        '---\ndoctype: report\nformat: doc\n---\n\n::: {#chart .section intent="chart"}\n## Survey\n\n'
        "Opening prose survives.\n\n" + DATA + "\nClosing prose survives.\n:::\n",
        encoding="utf-8",
    )
    version, _ = _build(working, capsys)
    copy = tmp_path / "report-reviewed.docx"
    shutil.copyfile(version / "report.docx", copy)
    document = WordDocument(str(copy))
    opening, reference, closing = document.paragraphs
    if change == "insert-before":
        reference.insert_paragraph_before("Added before the table.")
        expected = ["Opening prose survives.", "Added before the table.", "data", "Closing prose survives."]
    elif change == "delete-before":
        for run in opening.runs:
            run.text = ""
        expected = ["data", "Closing prose survives."]
    elif change == "split-before":
        opening.runs[0].text = "Opening prose"
        reference.insert_paragraph_before("survives.")
        expected = ["Opening prose", "survives.", "data", "Closing prose survives."]
    else:
        closing._p.addnext(reference._p)
        for mark in list(closing._p):
            if mark.tag == qn("w:bookmarkEnd"):
                reference._p.append(mark)
        expected = ["Opening prose survives.", "Closing prose survives.", "data"]
    document.save(str(copy))
    plan_path, plan = _read(copy, version, capsys)
    assert main(["review", "apply", str(working), "--plan", str(plan_path)]) == 0
    capsys.readouterr()
    rebuilt, facts = _build(working, capsys)
    assert REFERENCE not in " ".join(word["text"] for word in facts["words"])
    section = parse(working.read_text(encoding="utf-8"))[0].sections[0]
    assert section.paragraphs == [text for text in expected if text != "data"]
    fields = []
    index = 0
    for text in expected:
        if text == "data":
            fields.append("data")
        else:
            fields.append(f"paragraphs[{index}]")
            index += 1
    assert plan["sections"]["chart"]["content_order"] == fields
    assert section.ordered_content() == fields
    positions = []
    for field in fields:
        anchor = "data.categories[0]" if field == "data" else field
        marks = [mark for mark in facts["marks"] if mark.get("field") == anchor]
        assert marks
        positions.append(min((mark["page"], mark["y"]) for mark in marks))
    assert positions == sorted(positions)
    assert [p.text for p in WordDocument(str(rebuilt / "report.docx")).paragraphs] == [
        REFERENCE if text == "data" else text for text in expected
    ]


@pytest.mark.parametrize("literal_first", [False, True], ids=["literal-after", "literal-before"])
@pytest.mark.parametrize("legacy", [False, True], ids=["marked-reference", "older-copy"])
def test_chart_review_keeps_literal_prose_identical_to_its_generated_reference(tmp_path, capsys, literal_first, legacy):
    blocks = [REFERENCE, DATA] if literal_first else [DATA, REFERENCE]
    working = tmp_path / "report.md"
    working.write_text(
        '---\ndoctype: report\nformat: doc\n---\n\n::: {#chart .section intent="chart"}\n## Survey\n\n'
        + "\n\n".join(["Opening prose survives.", *blocks, "Closing prose survives."])
        + "\n:::\n",
        encoding="utf-8",
    )
    version, _ = _build(working, capsys)
    sent = version / "report.docx"
    if legacy:
        document = WordDocument(str(sent))
        for paragraph in document.paragraphs:
            if paragraph.text == REFERENCE:
                paragraph.style = "Normal"
        document.save(str(sent))
    copy = tmp_path / "report-reviewed.docx"
    shutil.copyfile(sent, copy)
    document = WordDocument(str(copy))
    document.paragraphs[0].runs[0].text = "Opening wording revised."
    document.save(str(copy))
    plan_path, _ = _read(copy, version, capsys)
    assert main(["review", "apply", str(working), "--plan", str(plan_path)]) == 0
    capsys.readouterr()
    _, facts = _build(working, capsys)
    section = parse(working.read_text(encoding="utf-8"))[0].sections[0]
    assert section.paragraphs == ["Opening wording revised.", REFERENCE, "Closing prose survives."]
    text = " ".join(word["text"] for word in facts["words"])
    assert text.count(REFERENCE) == 1
    assert section.ordered_content() == (
        ["paragraphs[0]", "paragraphs[1]", "data", "paragraphs[2]"]
        if literal_first
        else ["paragraphs[0]", "data", "paragraphs[1]", "paragraphs[2]"]
    )


def test_reference_only_chart_retains_presence_and_reports_reference_edits_as_unplaced(tmp_path, capsys):
    working = tmp_path / "report.md"
    working.write_text(
        '---\ndoctype: report\nformat: doc\n---\n\n::: {#chart .section intent="chart"}\n## Survey\n\n'
        + DATA
        + "\n:::\n",
        encoding="utf-8",
    )
    version, _ = _build(working, capsys)
    copy = tmp_path / "report-reviewed.docx"
    shutil.copyfile(version / "report.docx", copy)
    _, intact = _read(copy, version, capsys)
    assert intact["confirm"] == []
    assert intact["sections"]["chart"]["wording"] is None
    document = WordDocument(str(copy))
    document.paragraphs[0].runs[0].text = "Please revise the chart reference."
    document.save(str(copy))
    plan_path, plan = _read(copy, version, capsys)
    assert main(["review", "apply", str(working), "--plan", str(plan_path)]) == 0
    capsys.readouterr()
    _, facts = _build(working, capsys)
    assert plan["sections"]["chart"]["wording"] is None
    assert [(item["kind"], item["text"]) for item in plan["confirm"]] == [
        ("unplaced", "Please revise the chart reference.")
    ]
    text = " ".join(word["text"] for word in facts["words"])
    assert "Please revise" not in text
    assert "Upland" in text and "Lowland" in text
    for run in document.paragraphs[0].runs:
        run.text = ""
    document.save(str(copy))
    _, cleared = _read(copy, version, capsys)
    assert [item["section"] for item in cleared["confirm"] if item["kind"] == "delete"] == ["chart"]
