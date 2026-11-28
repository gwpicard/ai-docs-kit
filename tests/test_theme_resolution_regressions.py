"""Keep file diagnostics and the review sequence intact during theme selection."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = """---
doctype: report
format: doc
title: Trial scope
---

::: {#alpha01 .section intent="body"}
## Scope

The trial remains within scope.
:::
"""


@pytest.mark.parametrize("command", [("build",), ("check",), ("theme", "which")])
def test_theme_resolution_reports_the_undecodable_file_with_a_valid_control(tmp_path, command):
    source = tmp_path / "working file.md"
    source.write_text(SOURCE, encoding="utf-8")

    def run():
        return subprocess.run(
            [sys.executable, "-m", "ai_docs_kit.cli", *command, str(source)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=120,
        )

    valid = run()
    assert valid.returncode == 0, valid.stderr + valid.stdout
    assert valid.stderr == ""
    # A truncated multibyte character fails after a readable front matter prefix.
    source.write_bytes(SOURCE.encode("utf-8") + b"\xe2\x82")
    refused = run()
    assert refused.returncode == 2, refused.stderr + refused.stdout
    lines = refused.stderr.splitlines()
    assert len(lines) == 1, refused.stderr
    assert str(source) in lines[0] and "UTF-8" in lines[0], refused.stderr
    assert "Traceback" not in refused.stderr


def test_review_theme_selection_keeps_the_round_trip_in_order():
    text = (ROOT / "skills/review/SKILL.md").read_text(encoding="utf-8").lower()
    stages = ["review read", "classify", "review apply", "redraft", "build", "look"]
    positions = [text.index(stage) for stage in stages]
    assert positions == sorted(positions)
    selection = text.index("ai-docs-kit theme which")
    assert positions[0] < selection < positions[1]
    steps = dict(re.findall(r"^(\d+)\. (.*)$", text, re.MULTILINE))
    assert "--theme <folder>" in steps["6"]
