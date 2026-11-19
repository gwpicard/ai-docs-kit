"""Gathered facts extend the skill vocabulary without changing the core terms."""

from pathlib import Path


def test_gathered_facts_are_defined_in_the_skill_word_list():
    context = (Path(__file__).resolve().parents[1] / "CONTEXT.md").read_text(encoding="utf-8")
    core, _, skills = context.partition("## Skill words")
    definition = next((line for line in skills.splitlines() if line.startswith("- *Gathered facts*:")), "")
    assert definition, "define gathered facts alongside the words the skills add"
    for detail in ("source key", "optional locator", "working file"):
        assert detail in definition
    assert "Gathered facts" not in core
    assert "**Layout facts**" in core
