"""A refused replacement must preserve the rule already in the rulebook."""

import shutil

import yaml

from ai_docs_kit.cli import main
from ai_docs_kit.theme import NEUTRAL_ROOT


def test_failed_replacement_preserves_the_previously_adopted_rule(tmp_path):
    """Keep the adopted rule when its replacement has invalid provenance."""
    theme = tmp_path / "theme"
    shutil.copytree(NEUTRAL_ROOT, theme, ignore=shutil.ignore_patterns("exemplars"))
    source = tmp_path / "note.md"
    source.write_text(
        "---\ndoctype: report\nformat: doc\ntitle: Timing\n---\n\n"
        '::: {#timing .section intent="body"}\n## Timing\n\nReply ASAP.\n:::\n',
        encoding="utf-8",
    )
    assert main(["build", str(source), "--theme", str(theme)]) == 0
    proposal = tmp_path / "rule.yaml"
    rule = {
        "id": "feedback.date",
        "title": "Give a date",
        "origin": "feedback",
        "strength": "soft",
        "status": "proposed",
        "severity": "error",
        "tier": "source",
        "check": {"kind": "text-pattern", "field": "paragraphs", "regex": "ASAP"},
        "remedy": {"class": "redraft", "hint": "Give a date."},
        "provenance": {"label": "answered", "source": {"comment": "Give a date."}, "by": "Dana"},
    }
    proposal.write_text(yaml.safe_dump(rule), encoding="utf-8")
    test_args = [
        "rule",
        "test",
        str(proposal),
        "--example",
        f"{tmp_path / 'note.versions' / 'v1'}/timing",
        "--theme",
        str(theme),
    ]
    adopt_args = ["rule", "adopt", str(proposal), "--theme", str(theme)]
    assert main(test_args) == 0
    assert main(adopt_args) == 0
    adopted = theme / "rules" / "learned" / "feedback.date.yaml"
    original = adopted.read_bytes()

    # A malformed replacement may be refused at validation or at adoption.
    rule["provenance"]["source"]["comment"] = "   "
    proposal.write_text(yaml.safe_dump(rule), encoding="utf-8")
    if main(test_args) == 0:
        assert main(adopt_args) != 0

    assert adopted.is_file(), "refusing a replacement deleted the existing adopted rule"
    assert adopted.read_bytes() == original
