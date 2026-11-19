"""A broken proposed check names its file and problem before adoption writes anything."""

import shutil

import pytest
import yaml

from ai_docs_kit.cli import main
from ai_docs_kit.theme import NEUTRAL_ROOT


@pytest.mark.parametrize("field", ["paragraphs", "items"])
def test_adopt_reports_the_bad_regex_on_one_line(tmp_path, capsys, field):
    theme = tmp_path / "theme"
    shutil.copytree(NEUTRAL_ROOT, theme, ignore=shutil.ignore_patterns("exemplars"))
    path = tmp_path / "broken-rule.yaml"
    rule = {
        "id": "feedback.no-asap",
        "title": "Do not write ASAP",
        "origin": "feedback",
        "strength": "soft",
        "status": "proposed",
        "severity": "error",
        "tier": "source",
        "check": {"kind": "text-pattern", "field": field, "regex": "("},
        "remedy": {"class": "redraft", "hint": "Give a date instead."},
        "provenance": {"label": "answered", "source": {"comment": "Never write ASAP."}, "by": "Dana"},
    }
    path.write_text(yaml.safe_dump(rule), encoding="utf-8")

    assert main(["rule", "adopt", str(path), "--theme", str(theme)]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        f"{path}: not a valid rule: invalid regex '(': missing ), unterminated subpattern at position 0\n"
    )
    assert not (theme / "rules" / "learned").exists()
