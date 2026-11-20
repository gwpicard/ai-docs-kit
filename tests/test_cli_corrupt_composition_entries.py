"""Malformed section entries in a stored version are input errors at the CLI."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ai_docs_kit.cli import main


@pytest.mark.parametrize("command", ["rule test", "review apply"])
@pytest.mark.parametrize("entry", [None, "interrupted section", []])
def test_cli_refuses_malformed_composition_entries_cleanly(tmp_path, command, entry):
    source = tmp_path / "note.md"
    source.write_text(
        "---\ndoctype: report\nformat: doc\ntitle: Timing\n---\n\n"
        '::: {#timing .section intent="body"}\n## Timing\n\nReply ASAP about the plan.\n:::\n',
        encoding="utf-8",
    )
    assert main(["build", str(source)]) == 0
    before = source.read_bytes()
    version = tmp_path / "note.versions" / "v1"
    composition = version / "composition.json"
    saved = json.loads(composition.read_text(encoding="utf-8"))
    saved["sections"] = [entry]
    composition.write_text(json.dumps(saved), encoding="utf-8")
    if command == "rule test":
        rule = tmp_path / "rule.yaml"
        rule.write_text(
            "id: feedback.give-date\ntitle: Give a date\norigin: feedback\nstrength: soft\n"
            "status: proposed\nseverity: error\ntier: source\n"
            "check: {kind: text-pattern, field: paragraphs, regex: ASAP}\n"
            "remedy: {class: redraft, hint: Give a date.}\n"
            "provenance: {source: {comment: Give a date.}, by: Dana}\n",
            encoding="utf-8",
        )
        args = ["rule", "test", str(rule), "--example", f"{version}/timing"]
    else:
        plan = tmp_path / "decided.json"
        plan.write_text(
            json.dumps(
                {
                    "version": 1,
                    "review_copy": "note-reviewed.docx",
                    "sections": {"timing": {"title": None, "wording": "Revised wording.", "owner": "human"}},
                }
            ),
            encoding="utf-8",
        )
        args = ["review", "apply", str(source), "--plan", str(plan)]
    result = subprocess.run(
        [str(Path(sys.executable).with_name("ai-docs-kit")), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 2, result.stderr
    assert "composition.json" in result.stderr
    assert "Traceback" not in result.stderr
    assert len(result.stderr.strip().splitlines()) == 1
    assert source.read_bytes() == before
