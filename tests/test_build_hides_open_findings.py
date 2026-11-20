"""An ordinary build names its open errors and gaps before the version can go out."""

import json

from ai_docs_kit.cli import main

SOURCE = """---
doctype: pitch-deck
format: slides
title: Timing
---

::: {#timing .section intent="bullets"}
## Timing

- Confirm [GAP: the agreed date]. [S9 p.4]
- Record the decision.
- Check the scope.
:::
"""


def test_build_names_the_errors_and_gaps_it_records(tmp_path, capsys):
    source = tmp_path / "deck.md"
    source.write_text(SOURCE, encoding="utf-8")
    assert main(["build", str(source)]) == 0
    captured = capsys.readouterr()
    output = captured.out + captured.err
    version = tmp_path / "deck.versions" / "v1"
    manifest = json.loads((version / "manifest.json").read_text(encoding="utf-8"))
    findings = json.loads((version / "findings.json").read_text(encoding="utf-8"))
    errors = [finding for finding in findings if finding["severity"] == "error"]
    assert manifest["findings"]["error"] > 0 and errors
    assert manifest["gaps"] == [{"section": "timing", "text": "the agreed date"}]
    assert errors[0]["rule_id"] in output, output
    assert "timing" in output and "the agreed date" in output, output
