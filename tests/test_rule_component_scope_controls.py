"""Component-scoped rule tests use stored choices and check approved work too."""

import shutil

import pytest
import yaml

from ai_docs_kit.cli import main
from ai_docs_kit.theme import NEUTRAL_ROOT


def _source(fmt, intent, component):
    return (
        f"---\ndoctype: report\nformat: {fmt}\ntitle: Timing\n---\n\n"
        f'::: {{#other .section intent="{intent}"}}\n## Other\n\nReply ASAP.\n:::\n\n'
        f'::: {{#timing .section intent="{intent}" component="{component}" because="Prose layout"}}\n'
        "## Timing\n\nReply ASAP.\n:::\n"
    )


def _setup(tmp_path, fmt, intent, component):
    theme = tmp_path / "theme"
    shutil.copytree(NEUTRAL_ROOT, theme, ignore=shutil.ignore_patterns("exemplars"))
    source = tmp_path / "note.md"
    source.write_text(_source(fmt, intent, component), encoding="utf-8")
    assert main(["build", str(source), "--theme", str(theme)]) == 0
    rule = {
        "id": "feedback.component-date",
        "title": "Give a date",
        "origin": "feedback",
        "strength": "soft",
        "status": "proposed",
        "severity": "error",
        "tier": "source",
        "scope": {"components": [component]},
        "check": {"kind": "text-pattern", "field": "paragraphs", "regex": "ASAP"},
        "remedy": {"class": "redraft", "hint": "Give a date."},
        "provenance": {"label": "answered", "source": {"comment": "Give a date."}, "by": "Dana"},
    }
    proposed = tmp_path / "rule.yaml"
    proposed.write_text(yaml.safe_dump(rule), encoding="utf-8")
    argv = ["rule", "test", str(proposed), "--theme", str(theme), "--example"]
    return theme, source, argv, tmp_path / "note.versions" / "v1"


@pytest.mark.parametrize(
    ("fmt", "intent", "component"), [("doc", "callout", "body"), ("slides", "closing", "statement")]
)
def test_example_uses_its_stored_override_and_filters_other_components(tmp_path, capsys, fmt, intent, component):
    _, source, argv, version = _setup(tmp_path, fmt, intent, component)
    source.write_text(_source(fmt, component, intent).replace("ASAP", "by Friday"), encoding="utf-8")
    capsys.readouterr()

    assert main([*argv, f"{version}/timing"]) == 0
    assert "fires on v1/timing" in capsys.readouterr().out
    assert main([*argv, f"{version}/other"]) == 1
    assert "misses the example v1/other" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("fmt", "intent", "component"), [("doc", "callout", "body"), ("slides", "closing", "statement")]
)
@pytest.mark.parametrize("in_scope", [True, False], ids=["matching-component", "other-component"])
def test_approved_exemplars_obey_component_scope(tmp_path, capsys, fmt, intent, component, in_scope):
    theme, _, argv, version = _setup(tmp_path, fmt, intent, component)
    gold = theme / "exemplars" / "gold"
    gold.mkdir(parents=True)
    exemplar = _source(fmt, intent, component if in_scope else intent)
    (gold / "approved.md").write_text(exemplar, encoding="utf-8")
    capsys.readouterr()

    assert main([*argv, f"{version}/timing"]) == (1 if in_scope else 0)
    output = capsys.readouterr().out
    if in_scope:
        assert "hits the approved exemplar approved.md timing" in output
        assert "approved.md other" not in output
        assert main(["rule", "adopt", str(tmp_path / "rule.yaml"), "--theme", str(theme)]) == 1
    else:
        assert "fires on v1/timing and on no approved exemplar" in output
