"""The create skill carries the working-file grammar and the chooser's intent matrix.

The reference uses a Markdown table with Format and Allowed intents columns,
one row per format. Intent names are written as code or as comma-separated text.
"""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CREATE = ROOT / "skills" / "create"
REFERENCE = CREATE / "working-file.md"
CHOOSER = ROOT / "src" / "ai_docs_kit" / "render" / "chooser.yaml"


def _reference() -> str:
    assert REFERENCE.is_file(), "create needs a separate working-file.md reference, read when needed"
    return REFERENCE.read_text(encoding="utf-8")


def _intent_rows(text: str) -> dict[str, set[str]]:
    """Read the format rows, without depending on their order or code formatting."""
    rows: dict[str, set[str]] = {}
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip().strip("` ") for cell in line.strip().strip("|").split("|")]
        if cells[0] not in {"slides", "doc"}:
            continue
        assert len(cells) == 2, "use Format | Allowed intents rows in the reference table"
        assert cells[0] not in rows, f"duplicate reference table row for {cells[0]}"
        rows[cells[0]] = set(re.findall(r"[a-z][a-z0-9-]*", cells[1]))
    assert set(rows) == {"slides", "doc"}, "the reference table must cover both slides and doc"
    return rows


def _assert_format_intents(text: str, fmt: str, expected: set[str]) -> None:
    actual = _intent_rows(text)[fmt]
    assert actual == expected, (
        f"{fmt} reference differs from render/chooser.yaml: "
        f"missing={sorted(expected - actual)}, unknown or wrong format={sorted(actual - expected)}"
    )


@pytest.mark.parametrize(
    ("topic", "pattern"),
    [
        ("YAML front matter", r"(?m)^---\s*\n(?:[^\n]*\n)+?---\s*$"),
        ("doctype", r"(?m)^doctype:\s*\S+"),
        ("format", r"(?m)^format:\s*(?:slides|doc)\b"),
        ("title", r"(?m)^title:\s*\S+"),
        ("source list", r"(?m)^## Sources\s*\n\s*\n- \[[A-Za-z]+\d+\]\s+\S+"),
        ("section id and intent", r'(?m)^::: \{#[^\s}]+[^\n}]*\bintent=(?:"[a-z-]+"|[a-z-]+)[^\n}]*\}'),
        ("closing section fence", r"(?m)^:::\s*$"),
        ("citation with a page locator", r"\[[A-Za-z]+\d+\s+p\.\s*\d+\]"),
        ("citation with a timestamp", r"\[[A-Za-z]+\d+\s+\d{2}:\d{2}\]"),
        ("quoted because attribute", r'\bbecause="[^"\n]*\s+[^"\n]+"'),
        ("quoted redraft attribute", r'\bredraft="[^"\n]*\s+[^"\n]+"'),
    ],
)
def test_reference_documents_the_working_file_syntax(topic, pattern):
    assert re.search(pattern, _reference()), f"the reference needs a usable example of {topic}"


@pytest.mark.parametrize("fmt", ["slides", "doc"])
def test_reference_intent_table_matches_the_chooser(fmt):
    reference = _reference()
    rows = _intent_rows(reference)
    intents = yaml.safe_load(CHOOSER.read_text(encoding="utf-8"))["intents"]
    expected = {name for name, choices in intents.items() if fmt in choices}
    _assert_format_intents(reference, fmt, expected)

    # Seed both directions of drift, including an intent allowed in the other format.
    # These controls keep the table reader sensitive to missing and invented names.
    other_only = next(name for name, choices in intents.items() if fmt not in choices)
    for changed in (expected - {min(expected)}, expected | {"invented-intent"}, expected | {other_only}):
        seeded = f"| Format | Allowed intents |\n| --- | --- |\n| {fmt} | {', '.join(sorted(changed))} |\n"
        other = "doc" if fmt == "slides" else "slides"
        seeded += f"| {other} | {', '.join(sorted(rows[other]))} |\n"
        with pytest.raises(AssertionError, match="reference differs from render/chooser.yaml"):
            _assert_format_intents(seeded, fmt, expected)


@pytest.mark.parametrize("stage", ["outline", "draft"])
def test_outline_and_draft_point_to_the_reference_and_facts_add(stage):
    text = (CREATE / f"{stage}.md").read_text(encoding="utf-8")
    assert "working-file.md" in text, f"{stage} must tell the session to read the working-file reference"
    assert re.search(r"ai-docs-kit\s+facts\s+add\b", text), (
        f"{stage} must point to facts add for storing agreed facts before drafting"
    )
