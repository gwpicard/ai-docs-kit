"""Ordinary document review edits retain paragraph and item order through a rebuild."""

import json
import shutil
from pathlib import Path

import pytest
from docx import Document as WordDocument

from ai_docs_kit.cli import main
from ai_docs_kit.source import parse

INTENTS = ("body", "bullets", "callout", "key-numbers")
OPENING = "Opening prose survives."
CLOSING = "Closing prose survives."
ITEMS = ("42%: Survey coverage", "120: Completed visits", "53%: Next coverage")


def _build(working, capsys):
    assert main(["build", str(working)]) == 0
    version = Path(capsys.readouterr().out.strip().splitlines()[-1])
    return version, json.loads((version / "layout.json").read_bytes())


def _read(reviewed, version, capsys):
    assert main(["review", "read", str(reviewed)]) == 0
    capsys.readouterr()
    plan = version / "review-plan.json"
    return plan, json.loads(plan.read_bytes())


@pytest.mark.parametrize(
    ("edit", "source"),
    [
        ("delete-opening", ""),
        ("delete-opening", "Synthetic survey register."),
        ("delete-opening", CLOSING),
        ("insert-prose", CLOSING),
        ("delete-item", CLOSING),
        ("move-item", CLOSING),
    ],
)
def test_word_review_preserves_ordinary_section_order_and_excludes_source(tmp_path, capsys, edit, source):
    working = tmp_path / "report.md"
    sections = [
        f'::: {{#{intent} .section intent="{intent}"}}\n## Survey\n\n'
        f"{OPENING}\n\n- **42%** Survey coverage\n\n{CLOSING}\n\n"
        "- **120** Completed visits\n- **53%** Next coverage\n"
        + (f"\n> source: {source}\n" if source else "")
        + ":::\n"
        for intent in INTENTS
    ]
    working.write_text("---\ndoctype: report\nformat: doc\n---\n\n" + "\n".join(sections), encoding="utf-8")
    version, _ = _build(working, capsys)
    reviewed = tmp_path / "report-reviewed.docx"
    shutil.copyfile(version / "report.docx", reviewed)
    _, intact = _read(reviewed, version, capsys)
    assert intact["confirm"] == []
    assert all(section["content_order"] is None for section in intact["sections"].values())
    assert any(warning["code"] == "tracking_warning" for warning in intact["warnings"])

    document = WordDocument(str(reviewed))
    width = 7 if source else 6
    original = [OPENING, ITEMS[0], CLOSING, *ITEMS[1:]]
    expected = list(original)
    if edit == "delete-opening":
        expected.pop(0)
    elif edit == "insert-prose":
        expected.insert(1, "Added before the list.")
    elif edit == "delete-item":
        expected.pop(1)
    else:
        expected.insert(0, expected.pop(1))
    original_paragraphs = document.paragraphs
    for start in range(0, len(original_paragraphs), width):
        _, opening, first, closing, _, _ = original_paragraphs[start : start + 6]
        if edit == "delete-opening":
            for run in opening.runs:
                run.text = ""
        elif edit == "insert-prose":
            first.insert_paragraph_before("Added before the list.", style="Normal")
        elif edit == "delete-item":
            first._p.getparent().remove(first._p)
        else:
            opening._p.addprevious(first._p)
    document.save(str(reviewed))
    plan_path, plan = _read(reviewed, version, capsys)
    assert main(["review", "apply", str(working), "--plan", str(plan_path)]) == 0
    capsys.readouterr()
    rebuilt, facts = _build(working, capsys)

    fields = []
    paragraphs = []
    items = []
    for text in expected:
        target, kind = (items, "items") if text in ITEMS else (paragraphs, "paragraphs")
        fields.append(f"{kind}[{len(target)}]")
        target.append(text)
    for section in parse(working.read_text(encoding="utf-8"))[0].sections:
        words = sorted(
            [word for word in facts["words"] if word["section_id"] == section.id],
            key=lambda word: (word["box"]["page"], word["box"]["y0"], word["box"]["x0"]),
        )
        visible = " ".join(word["text"] for word in words)
        # Check the real PDF before inspecting the plan or saved source.
        positions = [visible.index(text.split(":")[0] if text in items else text) for text in expected]
        assert positions == sorted(positions), visible
        assert section.ordered_content() == fields
        assert section.paragraphs == paragraphs
        assert section.source_line == (source or None)
        assert plan["sections"][section.id]["content_order"] == fields
        assert plan["sections"][section.id]["owner"] == "human"
        for field in fields:
            anchor = field + ".head" if section.intent == "key-numbers" and field.startswith("items[") else field
            assert any(mark.get("field") == anchor and mark["id"] == section.id for mark in facts["marks"])
    assert plan["confirm"] == []
    expected_word = [line for _ in INTENTS for line in ["Survey", *expected, *([source] if source else [])]]
    assert [paragraph.text for paragraph in WordDocument(str(rebuilt / "report.docx")).paragraphs] == expected_word
