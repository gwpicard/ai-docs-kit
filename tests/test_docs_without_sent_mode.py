"""The design documents and skills describe the kit without the sent mode."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESIGN = (ROOT / "docs" / "DESIGN.md").read_text(encoding="utf-8")
ENGINE = (ROOT / "docs" / "ENGINE.md").read_text(encoding="utf-8")
SKILL_FILES = (
    "skills/create/ship.md",
    "skills/create/look.md",
    "skills/create/SKILL.md",
    "skills/review/SKILL.md",
)


def row(text: str, prefix: str) -> str:
    return next(line for line in text.splitlines() if line.startswith(prefix))


def test_design_never_requires_a_version_to_be_marked_sent():
    assert not re.search(r"\bsent\b", DESIGN, re.IGNORECASE)
    assert "ai-docs-kit sent" not in DESIGN


def test_design_principle_s7_and_rows_drop_the_sent_mark():
    for prefix in ("| S7 ", "| `create` ", "| `review` "):
        assert not re.search(r"\b(sent|marked)\b", row(DESIGN, prefix), re.IGNORECASE), prefix


def test_design_create_row_ends_with_the_look_summary():
    create = row(DESIGN, "| `create` ")
    assert re.search(r"summary|open error|not looked at", create, re.IGNORECASE)


def test_design_review_read_compares_with_the_version_it_came_from():
    start = DESIGN.index("`ai-docs-kit review read")
    section = DESIGN[start : start + 400]
    assert "version the copy came" in section


def test_engine_d1_notes_the_editable_copy_and_that_design_wins():
    d1 = row(ENGINE, "| D1 ")
    assert "No PPTX, DOCX" not in d1
    assert re.search(r"editable cop", d1, re.IGNORECASE)
    assert "DESIGN.md wins" in d1


def test_skills_do_not_tell_the_person_to_mark_a_version_sent_or_ready():
    for name in SKILL_FILES:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert not re.search(r"\bsent\b", text, re.IGNORECASE), name
        assert not re.search(r"mark\w*[^.\n]{0,40}\b(sent|ready)\b", text, re.IGNORECASE), name


def test_review_skill_names_missing_sections_from_review_apply():
    text = (ROOT / "skills/review/SKILL.md").read_text(encoding="utf-8")
    assert re.search(r"went missing|missing", text, re.IGNORECASE)
    assert re.search(r"changed since", text, re.IGNORECASE)
