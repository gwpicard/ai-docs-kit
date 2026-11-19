"""A cleared heading in a title-only section is refused before a plan is written."""

import json
import shutil

import pytest
from docx import Document

from ai_docs_kit.cli import main
from ai_docs_kit.source.parser import parse

SOURCE = """---
doctype: report
format: doc
title: Note
---

::: {#alpha01 .section intent="body"}
## Alpha
:::
"""


@pytest.mark.parametrize("heading", ["", "   ", "Alpha Prime"])
def test_review_read_checks_a_title_only_section(tmp_path, capsys, heading):
    source = tmp_path / "report.md"
    source.write_text(SOURCE, encoding="utf-8")
    assert main(["build", str(source)]) == 0
    version = tmp_path / "report.versions" / "v1"
    copy = tmp_path / "report-reviewed.docx"
    shutil.copyfile(version / "report.docx", copy)
    document = Document(str(copy))
    paragraph = next(p for p in document.paragraphs if p.style.name.startswith("Heading"))
    # Editing the run keeps the section bookmark in the otherwise empty paragraph.
    paragraph.runs[0].text = heading
    document.save(str(copy))
    capsys.readouterr()

    result = main(["review", "read", str(copy)])
    output = capsys.readouterr()
    plan_path = version / "review-plan.json"
    if not heading.strip():
        assert result == 2
        assert not plan_path.exists()
        assert "alpha01" in output.err and "title" in output.err.lower()
        assert len(output.err.strip().splitlines()) == 1
        assert "Traceback" not in output.err
        assert source.read_text(encoding="utf-8") == SOURCE
    else:
        assert result == 0, output.err
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        section = plan["sections"]["alpha01"]
        assert section["title"] == heading
        assert section["wording"] is None
        assert section["owner"] == "human"
        assert not plan["confirm"] and not plan["warnings"]
        assert "alpha01" in output.out and "title changed" in output.out
        assert main(["review", "apply", str(source), "--plan", str(plan_path)]) == 0
        applied, _ = parse(source.read_text(encoding="utf-8"))
        assert applied.sections[0].title == heading
        assert applied.sections[0].paragraphs == []
