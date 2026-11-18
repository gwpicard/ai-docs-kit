import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ("brand", "create", "review")
HEADINGS = ["## All skills", "## brand", "## create", "## review"]


def init(tmp_path, slug="acme"):
    return subprocess.run(
        [sys.executable, "-m", "ai_docs_kit.cli", "brand", "init", slug, "--root", str(tmp_path / ".brand")],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )


def text(skill):
    return (ROOT / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")


def test_brand_init_writes_preferences_with_four_headings_and_no_entries(tmp_path):
    assert init(tmp_path).returncode == 0
    lines = (tmp_path / ".brand" / "acme" / "preferences.md").read_text(encoding="utf-8").splitlines()
    assert [line for line in lines if line.startswith("#")] == HEADINGS
    assert not [line for line in lines if re.match(r"\s*[-*] ", line)]


def test_second_init_on_untouched_file_changes_nothing(tmp_path):
    init(tmp_path)
    path = tmp_path / ".brand" / "acme" / "preferences.md"
    before = path.read_bytes()
    init(tmp_path)
    assert path.read_bytes() == before


def test_second_init_keeps_an_entry_the_person_added(tmp_path):
    assert init(tmp_path).returncode == 0
    path = tmp_path / ".brand" / "acme" / "preferences.md"
    path.write_text(path.read_text(encoding="utf-8") + "- 2026-11-18: ask first\n", encoding="utf-8")
    before = path.read_bytes()
    init(tmp_path)
    assert path.read_bytes() == before


@pytest.mark.parametrize("skill", SKILLS)
def test_skill_reads_all_skills_and_own_section_before_first_step(skill):
    body = text(skill)
    assert "preferences.md" in body
    assert "## All skills" in body
    assert f"## {skill}" in body
    first_step = min(i for i in (body.find("## Steps"), body.find("## Stages")) if i >= 0)
    assert body.find("preferences.md") < first_step


@pytest.mark.parametrize("skill", SKILLS)
def test_skill_says_it_records_preferences_rather_than_being_edited(skill):
    body = text(skill).lower()
    assert re.search(r"records? (your |their |the person's )?preferences", body)
    assert "once" in body


@pytest.mark.parametrize("skill", SKILLS)
def test_skill_offers_three_kinds_of_record_after_two_corrections(skill):
    body = text(skill)
    lower = body.lower()
    assert "twice" in lower
    assert "- YYYY-MM-DD: " in body
    assert "rule" in lower
    assert "upstream issue" in lower


@pytest.mark.parametrize("skill", SKILLS)
def test_skill_never_edits_a_plugin_file(skill):
    assert re.search(r"never edit[^.\n]*plugin", text(skill).lower())


@pytest.mark.parametrize("skill", SKILLS)
def test_skill_files_an_upstream_issue_only_after_a_yes(skill):
    body = text(skill)
    lower = body.lower()
    assert "gh issue create --repo gwpicard/ai-docs-kit" in body
    assert "title" in lower and "body" in lower
    assert re.search(r"\byes\b", lower)
    assert "new-issue link" in lower or "new issue link" in lower
    assert "not signed in" in lower
    assert "general terms" in lower
    for word in ("brand material", "document text", "names", "file contents"):
        assert word in lower
