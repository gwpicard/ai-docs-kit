"""`rule test` turns a proposed rule with a broken check into exit 2 and a one-line message, not a traceback."""

from pathlib import Path

import pytest
import yaml

from ai_docs_kit.cli import main

NOTE = """---
doctype: report
format: doc
title: Note
---

::: {#bad01 .section intent="body"}
## Timing

Please reply ASAP about the plan.
:::
"""


def _rule(check: dict) -> dict:
    return {
        "id": "feedback.broken",
        "title": "Broken",
        "origin": "feedback",
        "strength": "soft",
        "status": "proposed",
        "severity": "error",
        "tier": "source",
        "check": check,
        "remedy": {"class": "redraft", "hint": "Give a date instead."},
        "provenance": {"label": "answered", "source": {"comment": "No."}, "by": "Dana"},
    }


@pytest.mark.parametrize(
    "check",
    [
        {"kind": "text-pattern", "field": "paragraphs", "regex": "("},
        {"kind": "no-such-check"},
        {"kind": "text-pattern", "field": "paragraphs"},
    ],
    ids=["bad-regex", "unknown-kind", "missing-regex"],
)
def test_a_broken_check_is_exit_2_not_a_traceback(tmp_path: Path, check):
    work = tmp_path / "work"
    work.mkdir()
    (work / "note.md").write_text(NOTE, encoding="utf-8")
    assert main(["build", str(work / "note.md")]) == 0
    path = tmp_path / "rule.yaml"
    path.write_text(yaml.safe_dump(_rule(check)), encoding="utf-8")
    code = main(["rule", "test", str(path), "--example", f"{work / 'note.versions' / 'v1'}/bad01"])
    assert code == 2
