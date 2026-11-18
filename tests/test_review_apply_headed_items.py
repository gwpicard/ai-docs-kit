"""A reviewer's edit to one headed bullet leaves the other headed bullets of the list as they were."""

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

::: {#list01 .section intent="body"}
## Findings

- **Cost:** First finding stands here
- **Risk:** Second finding stands here
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
    folder = tmp_path_factory.mktemp("headed")
    (folder / "report.md").write_text(SOURCE, encoding="utf-8")
    assert main(["build", str(folder / "report.md")]) == 0
    version = folder / "report.versions" / "v1"
    empty = folder / "none.json"
    empty.write_text("[]")
    assert main(["look", str(version), "--findings", str(empty)]) == 0
    assert main(["sent", str(version), "--to", "Reviewer"]) == 0
    return folder


def _items(folder: Path):
    doc, _ = parse((folder / "report.md").read_text(encoding="utf-8"))
    return next(s for s in doc.sections if s.id == "list01").items


def test_editing_one_headed_bullet_keeps_the_others(sent, tmp_path, capsys):
    work = tmp_path / "w"
    shutil.copytree(sent, work)
    before = _items(work)
    target = work / "report-reviewed.docx"
    document = Document(str(work / "report.versions" / "v1" / "report.docx"))
    second = next(p for p in document.paragraphs if "Second finding" in p.text)
    for run in second.runs[1:]:
        run.text = ""
    second.runs[0].text = f"{before[1].head}: Second finding was reworded"
    document.save(str(target))
    assert main(["review", "read", str(target)]) == 0
    out = capsys.readouterr().out
    plan_path = Path([line.split()[-1] for line in out.splitlines() if line.strip().endswith(".json")][-1])
    assert main(["review", "apply", str(work / "report.md"), "--plan", str(plan_path)]) == 0
    after = _items(work)
    assert after[0] == before[0]
    assert after[2] == before[2]
    assert after[1].head == before[1].head
    assert after[1].body == "Second finding was reworded"
