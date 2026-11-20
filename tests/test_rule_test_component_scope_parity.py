"""A proposed rule keeps its component scope when tested against a real version."""

import json
import shutil

import pytest
import yaml

from ai_docs_kit.cli import main
from ai_docs_kit.theme import NEUTRAL_ROOT


@pytest.mark.parametrize(
    ("fmt", "intent", "component"), [("doc", "body", "body"), ("slides", "statement", "statement")]
)
def test_rule_test_keeps_the_component_scope_seen_by_build(tmp_path, capsys, fmt, intent, component):
    theme = tmp_path / "theme"
    shutil.copytree(NEUTRAL_ROOT, theme, ignore=shutil.ignore_patterns("exemplars"))
    rule = {
        "id": "feedback.component-date",
        "title": "Give a date",
        "origin": "manual",
        "strength": "soft",
        "status": "active",
        "severity": "error",
        "tier": "source",
        "scope": {"components": [component]},
        "check": {"kind": "text-pattern", "field": "paragraphs", "regex": "ASAP"},
        "remedy": {"class": "redraft", "hint": "Give a date."},
        "provenance": {"label": "answered", "source": {"comment": "Give a date."}, "by": "Dana"},
    }
    authored = theme / "rules" / "authored"
    authored.mkdir(parents=True)
    (authored / "date.yaml").write_text(yaml.safe_dump(rule), encoding="utf-8")
    source = tmp_path / "note.md"
    source.write_text(
        f"---\ndoctype: report\nformat: {fmt}\ntitle: Timing\n---\n\n"
        f'::: {{#timing .section intent="{intent}"}}\n## Timing\n\nPlease reply ASAP about the plan.\n:::\n',
        encoding="utf-8",
    )
    assert main(["build", str(source), "--theme", str(theme)]) == 0
    version = tmp_path / "note.versions" / "v1"
    findings = json.loads((version / "findings.json").read_text(encoding="utf-8"))
    assert any(f["rule_id"] == rule["id"] and f["section_id"] == "timing" for f in findings)
    rule.update(origin="feedback", status="proposed")
    proposed = tmp_path / "proposed.yaml"
    proposed.write_text(yaml.safe_dump(rule), encoding="utf-8")
    capsys.readouterr()

    code = main(["rule", "test", str(proposed), "--example", f"{version}/timing", "--theme", str(theme)])

    captured = capsys.readouterr()
    assert code == 0, captured.out + captured.err
    assert "fires on v1/timing" in captured.out
