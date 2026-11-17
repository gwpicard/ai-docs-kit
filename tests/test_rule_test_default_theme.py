"""`rule test` without `--theme` leaves the plugin's neutral theme untouched."""

from pathlib import Path

import yaml

from ai_docs_kit.cli import main
from ai_docs_kit.theme import NEUTRAL_ROOT

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


def test_rule_test_without_a_theme_writes_nothing_under_the_neutral_theme(tmp_path: Path, capsys):
    work = tmp_path / "work"
    work.mkdir()
    (work / "note.md").write_text(NOTE, encoding="utf-8")
    assert main(["build", str(work / "note.md")]) == 0
    rule = {
        "id": "feedback.no-asap",
        "title": "Do not write ASAP",
        "origin": "feedback",
        "strength": "soft",
        "status": "proposed",
        "severity": "error",
        "tier": "source",
        "check": {"kind": "text-pattern", "field": "paragraphs", "regex": r"\bASAP\b"},
        "remedy": {"class": "redraft", "hint": "Give a date instead."},
        "provenance": {"label": "answered", "source": {"comment": "Never write ASAP."}, "by": "Dana"},
    }
    path = tmp_path / "rule.yaml"
    path.write_text(yaml.safe_dump(rule), encoding="utf-8")
    before = sorted(NEUTRAL_ROOT.rglob("*"))
    code = main(["rule", "test", str(path), "--example", f"{work / 'note.versions' / 'v1'}/bad01"])
    assert code == 0
    assert not (NEUTRAL_ROOT / "rules" / ".tested").exists()
    assert sorted(NEUTRAL_ROOT.rglob("*")) == before
