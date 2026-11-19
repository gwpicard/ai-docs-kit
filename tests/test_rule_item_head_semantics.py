"""Rule testing and checking agree on absent bullet heads and empty bodies."""

import json
import shutil

import yaml

from ai_docs_kit.cli import main
from ai_docs_kit.theme import NEUTRAL_ROOT

DECK = """---
doctype: report
format: slides
title: Timing
---

::: {#bul01 .section intent="bullets"}
## Timing

- Reply ASAP about the plan.
:::

::: {#empty01 .section intent="bullets"}
## Empty body

- **Timing**
:::
"""


def test_empty_pattern_rejects_absent_heads_but_detects_empty_bodies_through_the_cli(tmp_path):
    theme = tmp_path / "theme"
    shutil.copytree(NEUTRAL_ROOT, theme, ignore=shutil.ignore_patterns("exemplars"))
    (theme / "exemplars" / "gold").mkdir(parents=True)
    work = tmp_path / "deck.md"
    work.write_text(DECK, encoding="utf-8")
    assert main(["build", str(work), "--theme", str(theme)]) == 0
    version = tmp_path / "deck.versions" / "v1"
    composition = json.loads((version / "composition.json").read_text(encoding="utf-8"))
    assert composition["sections"][0]["props"]["items"][0]["head"] == ""

    path = tmp_path / "rule.yaml"
    rule = {
        "id": "feedback.empty-item",
        "title": "Give each bullet a body",
        "origin": "feedback",
        "strength": "soft",
        "status": "proposed",
        "severity": "error",
        "tier": "source",
        "check": {"kind": "text-pattern", "field": "items", "regex": "^$"},
        "remedy": {"class": "redraft", "hint": "Write the bullet's body."},
        "provenance": {"label": "answered", "source": {"comment": "No empty bullets."}, "by": "Dana"},
    }
    path.write_text(yaml.safe_dump(rule), encoding="utf-8")
    base = [str(path), "--theme", str(theme)]

    assert main(["rule", "test", *base, "--example", f"{version}/bul01"]) == 1
    assert main(["rule", "adopt", *base]) == 1
    assert not (theme / "rules" / "learned" / "feedback.empty-item.yaml").exists()

    assert main(["rule", "test", *base, "--example", f"{version}/empty01"]) == 0
    assert main(["rule", "adopt", *base]) == 0
    out = tmp_path / "checked"
    assert main(["check", str(work), "--theme", str(theme), "--out", str(out)]) == 0
    findings = json.loads((out / "deck.findings.json").read_text(encoding="utf-8"))
    hits = [finding for finding in findings if finding["rule_id"] == rule["id"]]
    assert [(finding["section_id"], finding["measured"]["text"]) for finding in hits] == [("empty01", "")]
