"""`rule test` builds the example with its own intent and keeps its markers out of git; the review
skill's learning step, run as written, ends with a rule on probation."""

import json
import re
import shlex
import shutil
from pathlib import Path

import pytest
import yaml

from ai_docs_kit.cli import main
from ai_docs_kit.theme import NEUTRAL_ROOT

SKILL = Path(__file__).resolve().parent.parent / "skills" / "review" / "SKILL.md"

DECK = """---
doctype: report
format: slides
title: Deck
---

::: {#bul01 .section intent="bullets"}
## Timing

- Reply ASAP about the plan.
- A second point.
:::
"""

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


def _rule(scope: dict | None = None) -> dict:
    rule = {
        "id": "feedback.no-asap",
        "title": "Do not write ASAP",
        "origin": "feedback",
        "strength": "soft",
        "status": "proposed",
        "severity": "error",
        "tier": "source",
        "check": {
            "kind": "text-pattern",
            "field": "items" if scope and scope.get("intents") == ["bullets"] else "paragraphs",
            "regex": r"\bASAP\b",
        },
        "remedy": {"class": "redraft", "hint": "Give a date instead."},
        "provenance": {"label": "answered", "source": {"comment": "Never write ASAP."}, "by": "Dana"},
    }
    if scope:
        rule["scope"] = scope
    return rule


def _write(path: Path, rule: dict) -> Path:
    path.write_text(yaml.safe_dump(rule), encoding="utf-8")
    return path


@pytest.fixture
def theme(tmp_path) -> Path:
    root = tmp_path / "theme"
    shutil.copytree(NEUTRAL_ROOT, root, ignore=shutil.ignore_patterns("exemplars"))
    (root / "exemplars" / "gold").mkdir(parents=True)
    return root


def _build(tmp_path: Path, theme: Path, text: str, name: str) -> Path:
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    (work / f"{name}.md").write_text(text, encoding="utf-8")
    assert main(["build", str(work / f"{name}.md"), "--theme", str(theme)]) == 0
    return work / f"{name}.versions" / "v1"


def test_a_rule_scoped_to_bullets_passes_on_a_bullets_example(tmp_path, theme):
    version = _build(tmp_path, theme, DECK, "deck")
    rule = _write(tmp_path / "rule.yaml", _rule({"intents": ["bullets"]}))
    argv = ["rule", "test", str(rule), "--example", f"{version}/bul01", "--theme", str(theme)]
    assert main(argv) == 0


def test_the_example_is_built_with_the_intent_the_composition_records(tmp_path, theme):
    version = tmp_path / "v1"
    version.mkdir()
    composition = {
        "format": "slides",
        "sections": [
            {
                "id": "bul01",
                "component": "bullets",
                "intent": "bullets",
                "props": {
                    "id": "bul01",
                    "title": "Timing",
                    "items": [{"head": "", "body": "Reply ASAP.", "cites": []}],
                    "paragraphs": [],
                },
            }
        ],
    }
    (version / "composition.json").write_text(json.dumps(composition), encoding="utf-8")
    scoped = _write(tmp_path / "bullets.yaml", _rule({"intents": ["bullets"]}))
    other = _write(tmp_path / "body.yaml", _rule({"intents": ["body"]}))
    base = ["--example", f"{version}/bul01", "--theme", str(theme)]
    assert main(["rule", "test", str(scoped), *base]) == 0
    assert main(["rule", "test", str(other), *base]) == 1


def test_a_body_scoped_rule_still_passes_on_a_body_example(tmp_path, theme):
    version = _build(tmp_path, theme, NOTE, "note")
    rule = _write(tmp_path / "rule.yaml", _rule({"intents": ["body"]}))
    assert main(["rule", "test", str(rule), "--example", f"{version}/bad01", "--theme", str(theme)]) == 0


def _marker_rule(tmp_path: Path, theme: Path) -> tuple[Path, Path]:
    version = _build(tmp_path, theme, NOTE, "note")
    return _write(tmp_path / "rule.yaml", _rule()), version


def _gitignore(theme: Path) -> list[str]:
    path = theme / "rules" / ".gitignore"
    return path.read_text(encoding="utf-8").splitlines() if path.is_file() else []


def test_a_marker_is_written_with_a_gitignore_that_lists_it(tmp_path, theme):
    rule, version = _marker_rule(tmp_path, theme)
    assert main(["rule", "test", str(rule), "--example", f"{version}/bad01", "--theme", str(theme)]) == 0
    assert any((theme / "rules" / ".tested").iterdir())
    assert [line.strip() for line in _gitignore(theme)].count(".tested/") == 1


def test_a_second_run_does_not_repeat_the_gitignore_line(tmp_path, theme):
    rule, version = _marker_rule(tmp_path, theme)
    argv = ["rule", "test", str(rule), "--example", f"{version}/bad01", "--theme", str(theme)]
    assert main(argv) == 0
    assert main(argv) == 0
    assert [line.strip() for line in _gitignore(theme)].count(".tested/") == 1


def test_existing_gitignore_lines_are_kept(tmp_path, theme):
    rule, version = _marker_rule(tmp_path, theme)
    (theme / "rules").mkdir(exist_ok=True)
    (theme / "rules" / ".gitignore").write_text("keep-me\n", encoding="utf-8")
    argv = ["rule", "test", str(rule), "--example", f"{version}/bad01", "--theme", str(theme)]
    assert main(argv) == 0
    lines = [line.strip() for line in _gitignore(theme)]
    assert "keep-me" in lines
    assert lines.count(".tested/") == 1


def test_no_gitignore_is_written_when_no_marker_is_written(tmp_path, theme):
    rule, version = _marker_rule(tmp_path, theme)
    missing = _write(tmp_path / "miss.yaml", _rule() | {"check": _rule()["check"] | {"regex": r"\bNEVER\b"}})
    argv = ["rule", "test", str(missing), "--example", f"{version}/bad01", "--theme", str(theme)]
    assert main(argv) == 1
    assert ".tested/" not in _gitignore(theme)


def _skill_command(verb: str) -> str:
    text = SKILL.read_text(encoding="utf-8")
    found = re.findall(rf"`(ai-docs-kit rule {verb} [^`]+)`", text)
    assert len(found) == 1, f"expected one `rule {verb}` command line in the skill"
    return found[0]


def _fill(line: str, values: dict[str, str]) -> list[str]:
    for placeholder, value in values.items():
        line = line.replace(placeholder, value)
    argv = shlex.split(line)
    assert argv[0] == "ai-docs-kit"
    assert not any("<" in part for part in argv), f"unfilled placeholder in {line!r}"
    return argv[1:]


def test_the_skills_learning_step_ends_with_a_rule_on_probation(tmp_path, theme):
    version = _build(tmp_path, theme, NOTE, "note")
    rule = _write(tmp_path / "rule.yaml", _rule())
    values = {
        "<rule>": str(rule),
        "<version>/<section>": f"{version}/bad01",
        "<brand theme>": str(theme),
    }
    assert main(_fill(_skill_command("test"), values)) == 0
    assert main(_fill(_skill_command("adopt"), values)) == 0
    learned = sorted((theme / "rules" / "learned").glob("*.yaml"))
    assert [p.stem for p in learned] == ["feedback.no-asap"]
    data = yaml.safe_load(learned[0].read_text(encoding="utf-8"))
    assert (data["origin"], data["status"]) == ("feedback", "probation")
