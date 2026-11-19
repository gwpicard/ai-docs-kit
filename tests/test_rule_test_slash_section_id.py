"""The rule command accepts every section id that a real build accepts."""

import json

import yaml

from ai_docs_kit.cli import main

SOURCE = """---
doctype: report
format: doc
title: Timing
---

::: {#part/timing .section intent="body"}
## Timing

Please reply ASAP about the meeting.
:::
"""


def test_rule_test_finds_a_section_whose_id_contains_a_slash(tmp_path, capsys):
    source = tmp_path / "note.md"
    source.write_text(SOURCE, encoding="utf-8")
    assert main(["build", str(source)]) == 0
    version = tmp_path / "note.versions" / "v1"
    composition = json.loads((version / "composition.json").read_text(encoding="utf-8"))
    assert composition["sections"][0]["id"] == "part/timing"
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
        "provenance": {"label": "answered", "source": {"comment": "Give a date."}, "by": "Dana"},
    }
    path = tmp_path / "rule.yaml"
    path.write_text(yaml.safe_dump(rule), encoding="utf-8")
    capsys.readouterr()
    code = main(["rule", "test", str(path), "--example", f"{version}/part/timing"])
    output = capsys.readouterr()
    assert code == 0, output.err
    assert "part/timing" in output.out
