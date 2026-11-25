"""A misspelt text field in a proposed rule is an input error at the command line."""

import subprocess
import sys
from pathlib import Path

import pytest
import yaml


def _run(*args):
    return subprocess.run(
        [str(Path(sys.executable).with_name("ai-docs-kit")), *map(str, args)],
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.mark.parametrize("field", ["paragraph", None, []])
def test_rule_test_refuses_unknown_text_fields_without_a_traceback(tmp_path, field):
    source = tmp_path / "note.md"
    source.write_text(
        "---\ndoctype: report\nformat: doc\ntitle: Note\n---\n\n"
        '::: {#timing .section intent="body"}\n## Timing\n\nReply ASAP about the plan.\n:::\n',
        encoding="utf-8",
    )
    built = _run("build", source)
    assert built.returncode == 0, built.stderr
    version = tmp_path / "note.versions" / "v1"
    rule = {
        "id": "feedback.give-date",
        "title": "Give a date",
        "origin": "feedback",
        "strength": "soft",
        "status": "proposed",
        "severity": "error",
        "tier": "source",
        "check": {"kind": "text-pattern", "field": "paragraphs", "regex": "ASAP"},
        "remedy": {"class": "redraft", "hint": "Give a date."},
        "provenance": {"source": {"comment": "Give a date."}, "by": "Dana"},
    }
    path = tmp_path / "rule.yaml"
    path.write_text(yaml.safe_dump(rule), encoding="utf-8")
    args = ("rule", "test", path, "--example", f"{version}/timing")
    control = _run(*args)
    assert control.returncode == 0, control.stderr
    rule["check"]["field"] = field
    path.write_text(yaml.safe_dump(rule), encoding="utf-8")

    result = _run(*args)

    assert result.returncode == 2, result.stderr
    assert str(path) in result.stderr
    assert "field" in result.stderr
    assert "Traceback" not in result.stderr
    assert len(result.stderr.strip().splitlines()) == 1
