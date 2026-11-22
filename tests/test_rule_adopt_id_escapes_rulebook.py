"""A rule id must never choose a path outside the learned rulebook."""

import shutil

import yaml

from ai_docs_kit.cli import main
from ai_docs_kit.theme import NEUTRAL_ROOT


def test_parent_segments_in_rule_id_cannot_destroy_theme_tokens(tmp_path):
    """Keep theme tokens intact after testing and adopting a path as an id."""
    theme = tmp_path / "theme"
    shutil.copytree(NEUTRAL_ROOT, theme, ignore=shutil.ignore_patterns("exemplars"))
    tokens = theme / "tokens.yaml"
    original = tokens.read_bytes()
    source = tmp_path / "note.md"
    source.write_text(
        "---\ndoctype: report\nformat: doc\ntitle: Timing\n---\n\n"
        '::: {#timing .section intent="body"}\n## Timing\n\nReply ASAP.\n:::\n',
        encoding="utf-8",
    )
    assert main(["build", str(source), "--theme", str(theme)]) == 0
    proposal = tmp_path / "rule.yaml"
    proposal.write_text(
        yaml.safe_dump(
            {
                "id": "../../tokens",
                "title": "Give a date",
                "origin": "feedback",
                "strength": "soft",
                "status": "proposed",
                "severity": "error",
                "tier": "source",
                "check": {"kind": "text-pattern", "field": "paragraphs", "regex": "ASAP"},
                "remedy": {"class": "redraft", "hint": "Give a date."},
                "provenance": {"source": {"comment": "Give a date."}, "by": "Dana"},
            }
        ),
        encoding="utf-8",
    )
    main(
        [
            "rule",
            "test",
            str(proposal),
            "--example",
            f"{tmp_path / 'note.versions' / 'v1'}/timing",
            "--theme",
            str(theme),
        ]
    )
    main(["rule", "adopt", str(proposal), "--theme", str(theme)])

    assert tokens.is_file(), "a rule id escaped rules/learned and deleted tokens.yaml"
    assert tokens.read_bytes() == original
