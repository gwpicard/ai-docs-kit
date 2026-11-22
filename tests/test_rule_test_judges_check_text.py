"""`rule test` judges a rule against exactly the text `check` sees (Issue 194)."""

import json
import re
import shutil
from pathlib import Path

import pytest
import yaml

from ai_docs_kit.cli import main
from ai_docs_kit.theme import NEUTRAL_ROOT

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "review" / "SKILL.md"
PLAN = ROOT / "PLAN.md"


def _rule(field: str, regex: str = r"\bASAP\b") -> dict:
    return {
        "id": "feedback.no-asap",
        "title": "Do not write ASAP",
        "origin": "feedback",
        "strength": "soft",
        "status": "proposed",
        "severity": "error",
        "tier": "source",
        "check": {"kind": "text-pattern", "field": field, "regex": regex},
        "remedy": {"class": "redraft", "hint": "Give a date instead."},
        "provenance": {"label": "answered", "source": {"comment": "Never write ASAP."}, "by": "Dana"},
    }


@pytest.fixture
def theme(tmp_path) -> Path:
    root = tmp_path / "theme"
    shutil.copytree(NEUTRAL_ROOT, root, ignore=shutil.ignore_patterns("exemplars"))
    (root / "exemplars" / "gold").mkdir(parents=True)
    return root


def _bullets_version(tmp_path: Path, item: dict) -> Path:
    version = tmp_path / "v1"
    version.mkdir()
    props = {"id": "bul01", "title": "Timing", "items": [item], "paragraphs": []}
    section = {"id": "bul01", "component": "bullets", "intent": "bullets", "props": props}
    composition = {"format": "slides", "sections": [section]}
    (version / "composition.json").write_text(json.dumps(composition), encoding="utf-8")
    return version


def _write(path: Path, rule: dict) -> Path:
    path.write_text(yaml.safe_dump(rule), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "item",
    [
        {"head": "", "body": "Reply ASAP.", "cites": []},
        {"head": "Timing", "body": "Reply ASAP, please.", "cites": []},
    ],
    ids=["body-only", "head-and-body"],
)
def test_a_paragraphs_rule_fails_on_a_bullets_example(tmp_path, theme, item):
    version = _bullets_version(tmp_path, item)
    rule = _write(tmp_path / "rule.yaml", _rule("paragraphs"))
    argv = ["rule", "test", str(rule), "--example", f"{version}/bul01", "--theme", str(theme)]
    assert main(argv) == 1


def test_an_items_rule_passes_on_a_bullets_example(tmp_path, theme):
    version = _bullets_version(tmp_path, {"head": "", "body": "Reply ASAP.", "cites": []})
    rule = _write(tmp_path / "rule.yaml", _rule("items"))
    argv = ["rule", "test", str(rule), "--example", f"{version}/bul01", "--theme", str(theme)]
    assert main(argv) == 0


def test_the_learning_step_proposes_field_items_for_a_bullet():
    text = SKILL.read_text(encoding="utf-8")
    assert re.search(r"field:\s*items", text), "the learning step must name `field: items` for a bullet"


def test_the_issue_124_deviation_no_longer_offers_item_text_as_paragraphs():
    lines = [line for line in PLAN.read_text(encoding="utf-8").splitlines() if line.startswith("- Issue 124:")]
    assert len(lines) == 1
    assert "offered as `paragraphs`" not in lines[0]


@pytest.mark.parametrize("field", ["paragraphs", "items"])
def test_adopt_of_a_rule_with_a_bad_regex_exits_2_with_one_line(tmp_path, theme, capsys, field):
    rule = _write(tmp_path / "broken-rule.yaml", _rule(field, regex="("))
    code = main(["rule", "adopt", str(rule), "--theme", str(theme)])
    captured = capsys.readouterr()
    lines = [line for line in (captured.out + captured.err).splitlines() if line.strip()]
    assert code == 2
    assert len(lines) == 1
    assert "broken-rule.yaml" in lines[0]
    assert not (theme / "rules" / "learned").exists() or not list((theme / "rules" / "learned").glob("*.yaml"))
