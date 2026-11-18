"""Headed bullets, sub-lines and citations go through the Word review round trip.

The path is `ai-docs-kit build`, an edit in python-docx, `review read`, then `review apply`.
"""

import shutil
from pathlib import Path

import pytest
from docx import Document

from ai_docs_kit.cli import main
from ai_docs_kit.source.parser import parse

SOURCE = """---
doctype: report
format: doc
title: Note
---

## Sources

- [S1] Finance ledger for the year

::: {#list01 .section intent="body"}
## Findings

- **Cost:** First finding stands here [S1 p. 4]
  - Sub line one of cost
  - Sub line two of cost
- **Risk:** Second finding stands here
  - Sub line of risk
- **Time:** Third finding stands here

The findings close with this paragraph, which keeps the page from being blank for the pixel checks.
:::

::: {#alpha01 .section intent="body"}
## Alpha

Alpha keeps its original wording here, and it runs a little longer so the page has ink.
:::
"""


@pytest.fixture(scope="module")
def sent(tmp_path_factory) -> Path:
    folder = tmp_path_factory.mktemp("roundtrip")
    (folder / "report.md").write_text(SOURCE, encoding="utf-8")
    assert main(["build", str(folder / "report.md")]) == 0
    empty = folder / "none.json"
    empty.write_text("[]")
    assert main(["look", str(folder / "report.versions" / "v1"), "--findings", str(empty)]) == 0
    return folder


@pytest.fixture
def work(sent, tmp_path) -> Path:
    shutil.copytree(sent, tmp_path / "w")
    return tmp_path / "w"


def _copy(work: Path) -> Document:
    return Document(str(work / "report.versions" / "v1" / "report.docx"))


def _paragraph(document, start: str):
    return next(p for p in document.paragraphs if p.text.startswith(start))


def _set(paragraph, text: str) -> None:
    for run in paragraph.runs[1:]:
        run.text = ""
    paragraph.runs[0].text = text


def _items(work: Path):
    doc, _ = parse((work / "report.md").read_text(encoding="utf-8"))
    return next(s for s in doc.sections if s.id == "list01").items


def _plan_path(work: Path, document, capsys) -> Path:
    target = work / "report-reviewed.docx"
    document.save(str(target))
    assert main(["review", "read", str(target)]) == 0
    out = capsys.readouterr().out
    return Path([line.split()[-1] for line in out.splitlines() if line.strip().endswith(".json")][-1])


def _apply(work: Path, plan_path: Path, capsys) -> str:
    assert main(["review", "apply", str(work / "report.md"), "--plan", str(plan_path)]) == 0
    return capsys.readouterr().out


def test_word_copy_writes_one_colon_after_the_head(work):
    texts = [p.text for p in _copy(work).paragraphs]
    assert any(t.startswith("Cost: First finding stands here") for t in texts), texts
    assert not any("::" in t for t in texts), texts


def test_editing_only_the_body_keeps_head_sub_lines_and_citations(work, capsys):
    before = _items(work)
    document = _copy(work)
    _set(_paragraph(document, "Cost:"), "Cost: First finding was reworded Sub line one of cost Sub line two of cost")
    plan_path = _plan_path(work, document, capsys)
    _apply(work, plan_path, capsys)
    after = _items(work)
    assert after[0].head == before[0].head
    assert after[0].body == "First finding was reworded"
    assert after[0].sub == before[0].sub
    assert after[0].citations == before[0].citations
    assert after[1:] == before[1:]


def test_editing_only_the_body_of_an_item_without_sub_lines(work, capsys):
    before = _items(work)
    document = _copy(work)
    _set(_paragraph(document, "Time:"), "Time: Third finding was reworded")
    _apply(work, _plan_path(work, document, capsys), capsys)
    after = _items(work)
    assert after[2].head == before[2].head
    assert after[2].body == "Third finding was reworded"
    assert after[:2] == before[:2]


def test_editing_the_head_applies_it_as_the_new_head(work, capsys):
    before = _items(work)
    document = _copy(work)
    _set(_paragraph(document, "Risk:"), "Exposure: Second finding stands here Sub line of risk")
    _apply(work, _plan_path(work, document, capsys), capsys)
    after = _items(work)
    assert after[1].head.rstrip(":") == "Exposure"
    assert after[1].body == "Second finding stands here"
    assert after[1].sub == before[1].sub
    assert after[0] == before[0]
    assert after[2] == before[2]


def test_a_sub_line_changed_since_the_version_is_named(work, capsys):
    document = _copy(work)
    _set(_paragraph(document, "Time:"), "Time: Third finding was reworded")
    plan_path = _plan_path(work, document, capsys)
    path = work / "report.md"
    text = path.read_text(encoding="utf-8")
    assert "Sub line of risk" in text
    path.write_text(text.replace("Sub line of risk", "Sub line edited later"), encoding="utf-8")
    out = _apply(work, plan_path, capsys)
    lines = [line for line in out.splitlines() if line.startswith("changed since v1")]
    assert len(lines) == 1, out
    assert "list01" in lines[0]
