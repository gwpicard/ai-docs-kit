"""Reference occurrence alignment must survive lost and inherited Word styles."""

import json
import shutil
from pathlib import Path

import pytest
from docx import Document as WordDocument

from ai_docs_kit.cli import main
from ai_docs_kit.source import parse

REFERENCE = "[Chart 1: Survey]"
SOURCE = """---
doctype: report
format: doc
---

::: {#chart .section intent="chart"}
## Survey

Opening prose survives.

```data
type: bar
category_label: District
categories: [Upland, Lowland]
series:
  - name: Completed
    values: [17, 29]
```

Closing prose survives.
:::
"""


def _build(working, capsys):
    assert main(["build", str(working)]) == 0
    version = Path(capsys.readouterr().out.strip().splitlines()[-1])
    return version, json.loads((version / "layout.json").read_text(encoding="utf-8"))


def _read(copy, version, capsys):
    assert main(["review", "read", str(copy)]) == 0
    capsys.readouterr()
    path = version / "review-plan.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("edit", ["reset-style", "inherited-style-before", "both-style-edits"])
def test_chart_reference_alignment_preserves_prose_and_data_after_style_edits(tmp_path, capsys, edit):
    working = tmp_path / "report.md"
    working.write_text(SOURCE, encoding="utf-8")
    version, _ = _build(working, capsys)
    copy = tmp_path / "report-reviewed.docx"
    shutil.copyfile(version / "report.docx", copy)
    _, intact = _read(copy, version, capsys)
    assert intact["sections"]["chart"]["wording"] is None
    assert intact["confirm"] == []

    document = WordDocument(str(copy))
    opening, reference, _ = document.paragraphs
    expected = ["Opening prose survives.", "Closing prose survives."]
    if edit != "reset-style":
        reference.insert_paragraph_before("Added before the table.", style=reference.style)
        expected.insert(1, "Added before the table.")
    if edit != "inherited-style-before":
        reference.style = "Normal"
        opening.runs[0].text = "Opening wording revised."
        expected[0] = "Opening wording revised."
    document.save(str(copy))
    plan_path, plan = _read(copy, version, capsys)
    assert main(["review", "apply", str(working), "--plan", str(plan_path)]) == 0
    capsys.readouterr()
    rebuilt, facts = _build(working, capsys)

    # Assert the real PDF first: a leaked reference must fail after the whole round trip.
    pdf_text = " ".join(word["text"] for word in facts["words"])
    assert REFERENCE not in pdf_text
    assert all(text in pdf_text for text in expected)
    assert plan["sections"]["chart"]["wording"].split("\n\n") == expected
    assert plan["confirm"] == [], "Inserted prose with the reference style is editable wording"
    section = parse(working.read_text(encoding="utf-8"))[0].sections[0]
    assert section.paragraphs == expected
    assert section.data["series"][0]["values"] == [17, 29]
    fields = [f"paragraphs[{i}]" for i in range(len(expected))]
    fields.insert(len(expected) - 1, "data")
    assert section.ordered_content() == fields
    positions = []
    for field in fields:
        anchor = "data.categories[0]" if field == "data" else field
        marks = [mark for mark in facts["marks"] if mark.get("field") == anchor and mark["id"] == "chart"]
        assert marks
        if field != "data":
            assert all(mark["role"] == "paragraph" for mark in marks)
        positions.append(min((mark["page"], mark["y"]) for mark in marks))
    assert positions == sorted(positions)
    expected_word = list(expected)
    expected_word.insert(len(expected) - 1, REFERENCE)
    assert [paragraph.text for paragraph in WordDocument(str(rebuilt / "report.docx")).paragraphs] == expected_word
    assert (rebuilt / "pages/p01.png").is_file()
