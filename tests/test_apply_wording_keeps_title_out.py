"""An accepted Word edit puts the reviewer's words in the paragraphs, not the heading text too."""

import json
import shutil

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

Alpha keeps its original wording here.
:::
"""


def test_applied_wording_does_not_copy_the_title_into_paragraphs(tmp_path, capsys):
    (tmp_path / "report.md").write_text(SOURCE, encoding="utf-8")
    assert main(["build", str(tmp_path / "report.md")]) == 0
    v1 = tmp_path / "report.versions" / "v1"
    empty = tmp_path / "none.json"
    empty.write_text("[]")
    assert main(["look", str(v1), "--findings", str(empty)]) == 0
    assert main(["sent", str(v1), "--to", "Reviewer"]) == 0
    capsys.readouterr()
    copy = tmp_path / "report-reviewed.docx"
    shutil.copyfile(v1 / "report.docx", copy)
    document = Document(str(copy))
    for paragraph in document.paragraphs:
        for run in paragraph.runs:
            run.text = run.text.replace("original wording", "reworded line")
    document.save(str(copy))
    assert main(["review", "read", str(copy)]) == 0
    plan_path = v1 / "review-plan.json"
    plans = list(v1.glob("*.json"))
    plan_file = next(p for p in plans if "plan" in p.name.lower())
    plan = json.loads(plan_file.read_text(encoding="utf-8"))
    assert plan["sections"]["alpha01"]["wording"]
    decided = tmp_path / "decided.json"
    decided.write_text(json.dumps(plan))
    assert main(["review", "apply", str(tmp_path / "report.md"), "--plan", str(decided)]) == 0
    doc, _ = parse((tmp_path / "report.md").read_text(encoding="utf-8"))
    section = next(s for s in doc.sections if s.id == "alpha01")
    assert section.title == "Alpha"
    assert "Alpha" not in section.paragraphs, section.paragraphs
    assert plan_path.name
