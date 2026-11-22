"""Rule commands refuse path separators before writing to the theme."""

import shutil

import pytest
import yaml

from ai_docs_kit.cli import main
from ai_docs_kit.theme import NEUTRAL_ROOT


@pytest.mark.parametrize("rule_id", ["feedback/nested", r"..\..\tokens"])
def test_rule_commands_refuse_path_ids_without_changing_the_theme(tmp_path, capsys, rule_id):
    theme = tmp_path / "theme"
    shutil.copytree(NEUTRAL_ROOT, theme, ignore=shutil.ignore_patterns("exemplars"))
    source = tmp_path / "note.md"
    source.write_text(
        "---\ndoctype: report\nformat: doc\ntitle: Timing\n---\n\n"
        '::: {#timing .section intent="body"}\n## Timing\n\nReply ASAP.\n:::\n',
        encoding="utf-8",
    )
    assert main(["build", str(source), "--theme", str(theme)]) == 0
    example = f"{tmp_path / 'note.versions' / 'v1'}/timing"
    proposal = tmp_path / "rule.yaml"
    data = {
        "id": "feedback.give-date",
        "title": "Give a date",
        "origin": "feedback",
        "strength": "soft",
        "severity": "error",
        "tier": "source",
        "check": {"kind": "text-pattern", "field": "paragraphs", "regex": "ASAP"},
        "remedy": {"class": "redraft", "hint": "Give a date."},
        "provenance": {"source": {"comment": "Give a date."}, "by": "Dana"},
    }
    proposal.write_text(yaml.safe_dump(data), encoding="utf-8")
    assert main(["rule", "test", str(proposal), "--example", example, "--theme", str(theme)]) == 0
    assert main(["rule", "adopt", str(proposal), "--theme", str(theme)]) == 0
    before = {path.relative_to(theme): path.read_bytes() for path in theme.rglob("*") if path.is_file()}
    data["id"] = rule_id
    proposal.write_text(yaml.safe_dump(data), encoding="utf-8")

    for command in ("test", "adopt"):
        capsys.readouterr()
        args = ["rule", command, str(proposal), "--theme", str(theme)]
        if command == "test":
            args += ["--example", example]
        assert main(args) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == f"{proposal}: not a valid rule: rule id must not contain path separators\n"
        after = {path.relative_to(theme): path.read_bytes() for path in theme.rglob("*") if path.is_file()}
        assert after == before
