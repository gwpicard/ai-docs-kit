"""A failed review apply must leave the working file and its history together."""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest


def _run(*args):
    return subprocess.run(
        [str(Path(sys.executable).with_name("ai-docs-kit")), *map(str, args)],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_review_apply_does_not_change_the_file_when_history_cannot_be_written(tmp_path):
    source = tmp_path / "note.md"
    source.write_text(
        "---\ndoctype: report\nformat: doc\ntitle: Note\n---\n\n"
        '::: {#timing .section intent="body"}\n## Timing\n\nReply about the plan.\n:::\n',
        encoding="utf-8",
    )
    built = _run("build", source)
    assert built.returncode == 0, built.stderr
    plan = {
        "version": 1,
        "review_copy": "note-reviewed.docx",
        "sections": {"timing": {"title": None, "wording": "The first revision.", "owner": "human"}},
    }
    decided = tmp_path / "decided.json"
    decided.write_text(json.dumps(plan), encoding="utf-8")
    control = _run("review", "apply", source, "--plan", decided)
    assert control.returncode == 0, control.stderr
    history = tmp_path / ".ai_docs_kit" / "oplog.jsonl"
    assert "The first revision." in history.read_text(encoding="utf-8")
    before_source, before_history = source.read_bytes(), history.read_bytes()
    plan["sections"]["timing"]["wording"] = "The second revision."
    decided.write_text(json.dumps(plan), encoding="utf-8")
    mode = stat.S_IMODE(history.stat().st_mode)
    history.chmod(mode & ~0o222)
    try:
        if os.access(history, os.W_OK):
            pytest.skip("The current user can write read-only files.")
        result = _run("review", "apply", source, "--plan", decided)
    finally:
        history.chmod(mode)

    assert result.returncode == 2, result.stderr
    assert "oplog.jsonl" in result.stderr and "Traceback" not in result.stderr
    assert history.read_bytes() == before_history
    assert source.read_bytes() == before_source, "A failed apply changed wording without recording its inverse."
