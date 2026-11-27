"""Saving and rebuilding mixed document content must preserve its reading order."""

import json
from pathlib import Path

import pytest
from docx import Document as WordDocument

from ai_docs_kit.cli import main

FRONT = "---\ndoctype: report\nformat: doc\n---\n\n"
DATA = """```data
type: bar
categories: [Upland, Lowland]
series:
  - name: Completed
    values: [17, 29]
```
"""


def _block(intent, content):
    return f'::: {{#mixed .section intent="{intent}"}}\n## Survey\n\n{content}\n:::\n'


def _build(working, capsys):
    assert main(["build", str(working)]) == 0
    version = Path(capsys.readouterr().out.strip().splitlines()[-1])
    facts = json.loads((version / "layout.json").read_text(encoding="utf-8"))
    return version, facts


def _positions(facts, text):
    words = sorted(
        [word for word in facts["words"] if word["section_id"] == "mixed"],
        key=lambda word: (word["box"]["page"], word["box"]["y0"], word["box"]["x0"]),
    )
    actual = " ".join(word["text"] for word in words)
    assert text in actual, actual
    return actual.index(text)


@pytest.mark.parametrize("intent", ["body", "bullets", "callout", "key-numbers", "chart"])
def test_section_get_put_twice_keeps_pdf_and_word_content_in_source_order(tmp_path, capsys, intent):
    opening, middle, closing = "Opening prose survives.", "Middle prose survives.", "Closing prose survives."
    if intent == "chart":
        content = f"{DATA}\n{opening}\n\n{closing}"
        pdf_order = ["Upland", opening, closing]
        word_order = ["[Chart 1: Survey]", opening, closing]
    elif intent == "key-numbers":
        content = f"{opening}\n\n- **42%** Survey coverage\n- **120** Completed visits\n\n{closing}"
        pdf_order = [opening, "42%", closing]
        word_order = ["Survey", opening, "42%: Survey coverage", "120: Completed visits", closing]
    else:
        content = (
            f"{opening}\n\n- Keep the access record.\n  - Retain the route sketch.\n\n"
            f"{middle}\n\n- Confirm the next visit.\n\n{closing}"
        )
        pdf_order = [
            opening,
            "Keep the access record.",
            "Retain the route sketch.",
            middle,
            "Confirm the next visit.",
            closing,
        ]
        word_order = [
            "Survey",
            opening,
            "Keep the access record. Retain the route sketch.",
            middle,
            "Confirm the next visit.",
            closing,
        ]
    working = tmp_path / "report.md"
    working.write_text(FRONT + _block(intent, content), encoding="utf-8")
    before = None
    for _ in range(2):
        assert main(["section", "get", str(working), "mixed"]) == 0
        replacement = tmp_path / "section.md"
        replacement.write_text(capsys.readouterr().out, encoding="utf-8")
        assert main(["section", "put", str(working), "mixed", "--from", str(replacement)]) == 0
        capsys.readouterr()
        saved = working.read_text(encoding="utf-8")
        if before is not None:
            assert saved == before
        before = saved
        version, facts = _build(working, capsys)
        positions = [_positions(facts, text) for text in pdf_order]
        assert positions == sorted(positions)
        lines = [paragraph.text for paragraph in WordDocument(str(version / "report.docx")).paragraphs]
        assert lines == word_order


def test_prose_between_figure_lists_stays_between_the_strips(tmp_path, capsys):
    content = (
        "- **42%** Survey coverage\n- **120** Completed visits\n\n"
        "Keep the next survey separate.\n\n"
        "- **53%** Next coverage\n- **130** Next visits"
    )
    working = tmp_path / "report.md"
    working.write_text(FRONT + _block("key-numbers", content), encoding="utf-8")
    version, facts = _build(working, capsys)
    positions = [_positions(facts, text) for text in ("42%", "Keep the next survey separate.", "53%")]
    assert positions == sorted(positions)
    values = [word for word in facts["words"] if word["role"] == "figure-value"]
    for pair in ({"42%", "120"}, {"53%", "130"}):
        assert len({word["box"]["page"] for word in values if word["text"] in pair}) == 1
    assert [p.text for p in WordDocument(str(version / "report.docx")).paragraphs] == [
        "Survey",
        "42%: Survey coverage",
        "120: Completed visits",
        "Keep the next survey separate.",
        "53%: Next coverage",
        "130: Next visits",
    ]
