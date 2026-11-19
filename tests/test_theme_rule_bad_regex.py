"""A theme rule whose text-pattern regex does not compile is exit 2 with a one-line message, not a traceback."""

import shutil
from pathlib import Path

import pytest
import yaml

from ai_docs_kit.cli import main
from ai_docs_kit.theme import NEUTRAL_ROOT

NOTE = """---
doctype: report
format: doc
title: Note
---

::: {#a0001 .section intent="body"}
## Timing

Hello there.
:::
"""


def test_a_theme_rule_with_a_bad_regex_is_exit_2(tmp_path: Path):
    theme = tmp_path / "theme"
    shutil.copytree(NEUTRAL_ROOT, theme)
    authored = theme / "rules" / "authored"
    authored.mkdir(parents=True, exist_ok=True)
    rule = {
        "id": "manual.bad-regex",
        "title": "Bad regex",
        "origin": "manual",
        "strength": "soft",
        "status": "active",
        "severity": "error",
        "tier": "source",
        "check": {"kind": "text-pattern", "field": "paragraphs", "regex": "("},
        "remedy": {"class": "redraft", "hint": "Fix it."},
        "provenance": {"source": {"doc": "x"}},
    }
    (authored / "bad.yaml").write_text(yaml.safe_dump(rule), encoding="utf-8")
    note = tmp_path / "note.md"
    note.write_text(NOTE, encoding="utf-8")
    try:
        code = main(["build", str(note), "--theme", str(theme)])
    except Exception as error:  # noqa: BLE001
        pytest.fail(f"traceback instead of exit 2: {error!r}")
    assert code == 2
