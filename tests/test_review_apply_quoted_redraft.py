"""A redraft ask keeps the reviewer's quoted wording when written to the working file."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from docx import Document

from ai_docs_kit.source.parser import parse


def _run(*args):
    return subprocess.run(
        [str(Path(sys.executable).with_name("ai-docs-kit")), *map(str, args)],
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.mark.parametrize("ask", ['Replace ASAP with "after lunch".', "Give a date.\nThen explain the timing."])
def test_review_apply_keeps_the_complete_redraft_ask(tmp_path, ask):
    source = tmp_path / "note.md"
    source.write_text(
        "---\ndoctype: report\nformat: doc\ntitle: Note\n---\n\n"
        '::: {#timing .section intent="body"}\n## Timing\n\nReply ASAP about the plan.\n:::\n',
        encoding="utf-8",
    )
    built = _run("build", source)
    assert built.returncode == 0, built.stderr
    version = tmp_path / "note.versions" / "v1"
    copy = tmp_path / "note-reviewed.docx"
    document = Document(str(version / "note.docx"))
    run = next(run for paragraph in document.paragraphs for run in paragraph.runs if "ASAP" in run.text)
    document.add_comment(run, text=ask, author="Dana")
    document.save(str(copy))
    read = _run("review", "read", copy)
    assert read.returncode == 0, read.stderr
    plan = json.loads((version / "review-plan.json").read_text(encoding="utf-8"))
    comment = plan["sections"]["timing"]["confirm"][0]
    assert comment["text"] == ask
    decided = tmp_path / "decided.json"

    # The ordinary ask is a control through the same command and plan.
    comment.update(accepted=True, action="redraft", ask="Give a date.")
    decided.write_text(json.dumps(plan), encoding="utf-8")
    control = _run("review", "apply", source, "--plan", decided)
    assert control.returncode == 0, control.stderr
    control_doc, _ = parse(source.read_text(encoding="utf-8"))
    assert control_doc.sections[0].redraft == "Give a date."

    comment["ask"] = ask
    decided.write_text(json.dumps(plan), encoding="utf-8")
    result = _run("review", "apply", source, "--plan", decided)
    assert result.returncode == 0, result.stderr
    doc, findings = parse(source.read_text(encoding="utf-8"))
    assert [section.id for section in doc.sections] == ["timing"], findings
    assert doc.sections[0].redraft == ask
    assert doc.sections[0].paragraphs == ["Reply ASAP about the plan."]
    assert doc.sections[0].owner != "human"
