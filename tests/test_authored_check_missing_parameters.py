"""Incomplete authored checks are input errors rather than command tracebacks."""

import shutil
import subprocess
import sys

import pytest
import yaml

from ai_docs_kit.theme import NEUTRAL_ROOT


def _run(*args):
    return subprocess.run(
        [sys.executable, "-m", "ai_docs_kit.cli", *map(str, args)],
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.mark.parametrize("command", ["build", "check"])
@pytest.mark.parametrize(
    "check",
    [
        {"kind": "text-pattern", "field": "paragraphs"},
        {"kind": "not", "checks": []},
        {"kind": "not", "checks": [{"kind": "empty-section"}, {"kind": "empty-section"}]},
    ],
    ids=["missing-regex", "not-without-child", "not-with-two-children"],
)
def test_incomplete_authored_check_is_refused_cleanly(tmp_path, command, check):
    theme = tmp_path / "theme"
    shutil.copytree(NEUTRAL_ROOT, theme, ignore=shutil.ignore_patterns("exemplars"))
    authored = theme / "rules" / "authored"
    authored.mkdir(parents=True)
    rule = {
        "id": "manual.give-date",
        "title": "Give a date",
        "origin": "manual",
        "strength": "soft",
        "status": "active",
        "severity": "error",
        "tier": "source",
        "check": {"kind": "text-pattern", "field": "paragraphs", "regex": "ASAP"},
        "remedy": {"class": "redraft", "hint": "Give a date."},
        "provenance": {"by": "Dana"},
    }
    path = authored / "give-date.yaml"
    path.write_text(yaml.safe_dump(rule), encoding="utf-8")
    source = tmp_path / "note.md"
    source.write_text(
        "---\ndoctype: report\nformat: doc\ntitle: Note\n---\n\n"
        '::: {#timing .section intent="body"}\n## Timing\n\nThe plan names a date.\n:::\n',
        encoding="utf-8",
    )
    control = _run(command, source, "--theme", theme, "--out", tmp_path / "control")
    assert control.returncode == 0, control.stderr
    rule["check"] = check
    path.write_text(yaml.safe_dump(rule), encoding="utf-8")
    before = path.read_bytes(), source.read_bytes()

    result = _run(command, source, "--theme", theme, "--out", tmp_path / "invalid")

    assert result.returncode == 2, result.stderr or result.stdout
    assert "give-date.yaml" in result.stderr
    assert "Traceback" not in result.stderr
    assert len(result.stderr.strip().splitlines()) == 1
    assert (path.read_bytes(), source.read_bytes()) == before
