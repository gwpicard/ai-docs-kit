# Intent: AGENTS.md gives agents the repository layout, commands and working rules while keeping the loop settings intact.
from pathlib import Path

AGENTS = Path(__file__).resolve().parents[2] / "AGENTS.md"

# The settings AI Loop Kit 2 reads from the `## Loop` section. The person may tune their
# values; each key must stay present.
LOOP_KEYS = ["Prepare command", "Test command", "Test files command", "Loop branch"]


def _text() -> str:
    return AGENTS.read_text(encoding="utf-8")


def _section(heading: str) -> str | None:
    """Return the body of a `## heading` section, or None when it is absent."""
    lines = _text().splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        if line.rstrip("\n") == f"## {heading}":
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    return "".join(lines[start:end])


def _has_all(text: str, needles: list[str]) -> list[str]:
    lowered = text.lower()
    return [n for n in needles if n.lower() not in lowered]


def test_D1_loop_section_unchanged():
    section = _section("Loop")
    assert section is not None, "AGENTS.md must keep a '## Loop' section"
    assert section.startswith("## Loop\n")
    present = {line.split(":", 1)[0] for line in section.splitlines()}
    missing = [k for k in LOOP_KEYS if k not in present]
    assert not missing, f"loop settings missing: {missing}"
    assert "Prepare command: `uv sync" in section
    assert "Test command: `uv run python -m pytest`" in section


def test_D1_title_lines_kept():
    text = _text()
    assert text.startswith(
        "# ai-docs-kit\n\nClaude skills that write branded reports and decks as PDF, check every build against a brand"
        " rulebook, and learn from comments in Word and PowerPoint. Early development.\n"
    )


def test_D2_repository_section_names_docs_and_commands():
    section = _section("Repository")
    assert section is not None, "AGENTS.md must have a '## Repository' section"
    missing = _has_all(
        section,
        [
            "CONTEXT.md",
            "docs/DESIGN.md",
            "docs/ENGINE.md",
            "PLAN.md",
            "uv sync",
            "uv run python -m pytest",
            "uv run ruff check .",
            "uv run ruff format --check .",
            "uv run mypy",
            "uv run ai-docs-kit doctor",
        ],
    )
    assert missing == []


def test_D2_repository_section_lists_layout():
    section = _section("Repository")
    assert section is not None, "AGENTS.md must have a '## Repository' section"
    missing = _has_all(
        section,
        ["src/ai_docs_kit/", "tests/", "tests/judge/", "tests/fixtures/", "scripts/", "docs/"],
    )
    assert missing == []


def test_D3_working_rules_seeded_defect_pages_cassette():
    section = _section("Working rules")
    assert section is not None, "AGENTS.md must have a '## Working rules' section"
    missing = _has_all(section, ["seeded defect", "rendered pages", "cassette"])
    assert missing == []


def test_D4_working_rules_generated_licence_dependency_dco():
    section = _section("Working rules")
    assert section is not None, "AGENTS.md must have a '## Working rules' section"
    missing = _has_all(
        section,
        ["generated files", "fonts", "recorded licence", "licence check", "DCO", "git commit -s"],
    )
    assert missing == []


def test_D5_working_rules_language_and_attribution():
    section = _section("Working rules")
    assert section is not None, "AGENTS.md must have a '## Working rules' section"
    missing = _has_all(section, ["British English", "em dash", "attribution"])
    assert missing == []
