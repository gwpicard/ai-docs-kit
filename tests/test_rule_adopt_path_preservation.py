"""Testing and adopting a rule must preserve files outside rules/learned."""

import shutil

import pytest
import yaml

from ai_docs_kit.cli import main
from ai_docs_kit.theme import NEUTRAL_ROOT


def _rule(rule_id, origin="feedback"):
    return {
        "id": rule_id,
        "title": "Give a date",
        "origin": origin,
        "strength": "soft",
        "status": "proposed",
        "severity": "error",
        "tier": "source",
        "check": {"kind": "text-pattern", "field": "paragraphs", "regex": "ASAP"},
        "remedy": {"class": "redraft", "hint": "Give a date."},
        "provenance": {"source": {"comment": "Give a date."}, "by": "Dana"},
    }


@pytest.mark.parametrize("destination", ["authored", "project", "absolute", "nested-parent"])
def test_rule_adoption_preserves_files_outside_learned(tmp_path, destination):
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
    proposal = tmp_path / "proposal.yaml"

    # Establish that a normal rule can still be tested and adopted on probation.
    proposal.write_text(yaml.safe_dump(_rule("feedback.give-date")), encoding="utf-8")
    assert main(["rule", "test", str(proposal), "--example", example, "--theme", str(theme)]) == 0
    assert main(["rule", "adopt", str(proposal), "--theme", str(theme)]) == 0
    learned = theme / "rules" / "learned" / "feedback.give-date.yaml"
    data = yaml.safe_load(learned.read_text(encoding="utf-8"))
    assert (data["id"], data["origin"], data["status"]) == (
        "feedback.give-date",
        "feedback",
        "probation",
    )
    learned_before = learned.read_bytes()

    if destination == "authored":
        victim = theme / "rules" / "authored" / "kept.yaml"
        victim.parent.mkdir(parents=True, exist_ok=True)
        victim.write_text(yaml.safe_dump(_rule("manual.kept", origin="manual")), encoding="utf-8")
        rule_id = "../authored/kept"
    elif destination == "nested-parent":
        victim = theme / "tokens.yaml"
        rule_id = "nested/../../../tokens"
    else:
        victim = tmp_path / "outside.yaml"
        victim.write_text("purpose: Keep this project data.\n", encoding="utf-8")
        rule_id = "../../../outside" if destination == "project" else str(victim.with_suffix(""))
    original = victim.read_bytes()
    proposal.write_text(yaml.safe_dump(_rule(rule_id)), encoding="utf-8")

    # Refusal or safe storage is acceptable; neither command may alter the victim.
    main(["rule", "test", str(proposal), "--example", example, "--theme", str(theme)])
    assert victim.is_file(), "rule test removed a file outside rules/learned"
    assert victim.read_bytes() == original, "rule test overwrote a file outside rules/learned"
    main(["rule", "adopt", str(proposal), "--theme", str(theme)])
    assert victim.is_file(), "rule adopt removed a file outside rules/learned"
    assert victim.read_bytes() == original, "rule adopt overwrote a file outside rules/learned"
    assert learned.read_bytes() == learned_before
