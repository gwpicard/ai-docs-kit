"""Spoken rules see the same text in a built version and in check."""

import json
import shutil

import pytest
import yaml

from ai_docs_kit.cli import main
from ai_docs_kit.theme import NEUTRAL_ROOT


@pytest.mark.parametrize(("fmt", "intent"), [("slides", "statement"), ("doc", "body")])
def test_spoken_text_survives_build_testing_adoption_and_check(tmp_path, fmt, intent):
    theme = tmp_path / "theme"
    shutil.copytree(NEUTRAL_ROOT, theme, ignore=shutil.ignore_patterns("exemplars"))
    (theme / "exemplars" / "gold").mkdir(parents=True)
    work = tmp_path / "speech.md"
    work.write_text(
        f"""---
doctype: report
format: {fmt}
title: Timing
---

::: {{#speech .section intent="{intent}"}}
## Timing

The plan has a date.
> spoken: SpeechToken
:::

::: {{#silent .section intent="{intent}"}}
## Written only

SpeechToken appears in a paragraph.
:::

::: {{#empty .section intent="{intent}"}}
## Empty speech

The plan has a date.
> spoken:
:::
""",
        encoding="utf-8",
    )
    assert main(["build", str(work), "--theme", str(theme)]) == 0
    version = tmp_path / "speech.versions" / "v1"
    path = tmp_path / "rule.yaml"
    rule = {
        "id": "feedback.spoken",
        "title": "Avoid SpeechToken in speech",
        "origin": "feedback",
        "strength": "soft",
        "status": "proposed",
        "severity": "error",
        "tier": "source",
        "check": {"kind": "text-pattern", "field": "spoken", "regex": "SpeechToken"},
        "remedy": {"class": "redraft", "hint": "Use the approved wording."},
        "provenance": {"label": "answered", "source": {"comment": "Avoid SpeechToken."}, "by": "Dana"},
    }
    path.write_text(yaml.safe_dump(rule), encoding="utf-8")
    base = [str(path), "--theme", str(theme)]
    for section_id in ("silent", "empty"):
        assert main(["rule", "test", *base, "--example", f"{version}/{section_id}"]) == 1
    assert main(["rule", "test", *base, "--example", f"{version}/speech"]) == 0
    assert main(["rule", "adopt", *base]) == 0

    composition = json.loads((version / "composition.json").read_text(encoding="utf-8"))
    assert composition["sections"][0]["props"]["spoken"] == "SpeechToken"
    out = tmp_path / "checked"
    assert main(["check", str(work), "--theme", str(theme), "--out", str(out)]) == 0
    findings = json.loads((out / "speech.findings.json").read_text(encoding="utf-8"))
    hits = [finding for finding in findings if finding["rule_id"] == rule["id"]]
    assert [(finding["section_id"], finding["measured"]["text"]) for finding in hits] == [("speech", "SpeechToken")]

    # Testing uses the stored version even after the working file's speech changes.
    work.write_text(
        work.read_text(encoding="utf-8").replace("> spoken: SpeechToken", "> spoken: ChangedToken"),
        encoding="utf-8",
    )
    assert main(["rule", "test", *base, "--example", f"{version}/speech"]) == 0
