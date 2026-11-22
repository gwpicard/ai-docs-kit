"""YAML scalars that are not regex strings receive a clean CLI diagnostic."""

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from ai_docs_kit.cli import main


@pytest.mark.parametrize("regex", [42, True, None])
def test_rule_test_refuses_a_non_string_regex_without_a_traceback(tmp_path, regex):
    source = tmp_path / "note.md"
    source.write_text(
        "---\ndoctype: report\nformat: doc\ntitle: Timing\n---\n\n"
        '::: {#timing .section intent="body"}\n## Timing\n\nReply ASAP about the plan.\n:::\n',
        encoding="utf-8",
    )
    assert main(["build", str(source)]) == 0
    rule = tmp_path / "numeric-regex.yaml"
    rule.write_text(
        yaml.safe_dump(
            {
                "id": "feedback.give-date",
                "title": "Give a date",
                "origin": "feedback",
                "strength": "soft",
                "status": "proposed",
                "severity": "error",
                "tier": "source",
                "check": {"kind": "text-pattern", "field": "paragraphs", "regex": regex},
                "remedy": {"class": "redraft", "hint": "Give a date."},
                "provenance": {"source": {"comment": "Give a date."}, "by": "Dana"},
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            str(Path(sys.executable).with_name("ai-docs-kit")),
            "rule",
            "test",
            str(rule),
            "--example",
            f"{tmp_path / 'note.versions' / 'v1'}/timing",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 2, result.stderr
    assert "numeric-regex.yaml" in result.stderr
    assert "Traceback" not in result.stderr
    assert len(result.stderr.strip().splitlines()) == 1
