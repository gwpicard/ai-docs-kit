"""Issue 370: the create stages teach traceable calculations in both authoring places."""

import json
import re
from pathlib import Path

import pytest

from ai_docs_kit.loop.guards import CALC

CREATE = Path(__file__).resolve().parents[1] / "skills" / "create"
CITATION = re.compile(r'\[[A-Za-z]+\d+(?:[^\]\n]*)\]|"source"\s*:\s*"[A-Za-z]+\d+"')


def _calc_examples(text):
    # Accept Markdown lines, inline code and JSON strings without prescribing example values.
    for match in re.finditer(
        r"calc:\s*(?:sum|difference|ratio|percentage)\([^()\n]*\)\s*=\s*[-+]?\d[\d,]*(?:\.\d+)?%?", text
    ):
        if CALC.fullmatch(match.group()):
            yield match


@pytest.mark.parametrize("stage", ["outline.md", "working-file.md"])
def test_create_stage_explains_calc_with_cited_facts_and_plain_derivation_refusal(stage):
    text = (CREATE / stage).read_text(encoding="utf-8")
    examples = list(_calc_examples(text))
    assert examples, f"{stage} needs a usable calc: example in the guard's grammar"
    assert any(CITATION.search(text[max(0, example.start() - 800) : example.end() + 800]) for example in examples), (
        f"{stage}'s calculation example must cite the facts supplying its operands"
    )
    prose = " ".join(text.lower().replace("`", "").split())
    assert re.search(r"(?:deriv\w*|calculat\w*|comput\w*)", prose), f"{stage} must explain derived figures"
    assert any(
        "facts add" in paragraph
        and re.search(r"refus\w*|reject\w*", paragraph)
        and re.search(r"plain|ordinary|direct|source does not state|source never states", paragraph)
        for paragraph in (" ".join(part.lower().replace("`", "").split()) for part in text.split("\n\n"))
    ), f"{stage} must say that facts add refuses derived figures stored as plain facts"


def test_working_file_reference_shows_a_stored_calc_fact_and_a_note_beside_the_figure():
    text = (CREATE / "working-file.md").read_text(encoding="utf-8")
    stored = []
    for block in re.findall(r"```json\s*\n(.*?)\n```", text, re.DOTALL):
        try:
            value = json.loads(block)
        except ValueError:
            continue
        if isinstance(value, list):
            stored.extend(fact for fact in value if isinstance(fact, dict))
    calculations = [fact for fact in stored if isinstance(fact.get("text"), str) and CALC.fullmatch(fact["text"])]
    assert calculations, "show the calc: line as a text entry in the facts JSON, with its source key"
    assert all(re.fullmatch(r"[A-Za-z]+\d+", fact.get("source", "")) for fact in calculations)
    notes = re.findall(r"(?m)^>\s*note:\s*(calc:[^\n]+)", text)
    assert any(CALC.fullmatch(line.strip()) for line in notes), "also show the calc: line in a section's > note:"
    assert any(
        CITATION.search(text[max(0, example.start() - 800) : example.end() + 800])
        for example in re.finditer(r"(?m)^>\s*note:\s*calc:", text)
    ), "the note example must keep the operand citations beside the figure"
