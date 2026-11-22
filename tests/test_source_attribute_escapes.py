"""Quoted source attributes preserve text through canonical serialisation."""

import pytest

from ai_docs_kit.model import Document, Section
from ai_docs_kit.source import parse, serialise


@pytest.mark.parametrize(
    "value",
    [
        'Replace ASAP with "after lunch".',
        "Give a date.\nThen explain the timing.",
        'Use "Friday".\r\n\tKeep \\n literal and C:\\notes\\timing.',
        'Keep } #other intent="quote" and\n::: inside the ask.',
        "",
    ],
)
def test_quoted_attributes_round_trip(value):
    section = Section(
        id="timing",
        intent="body",
        redraft=value,
        because=value,
        extra_attrs={"custom": value},
        paragraphs=["Reply ASAP about the plan."],
    )
    original = Document(front={"doctype": "report"}, format="doc", sections=[section])
    text = serialise(original)
    opening = next(line for line in text.splitlines() if line.startswith("::: {"))
    assert opening.endswith('"}')
    restored, findings = parse(text)
    assert restored == original, findings
    assert serialise(restored) == text


def test_unrecognised_escapes_and_bare_values_stay_literal():
    text = '---\nformat: doc\n---\n\n::: {#timing .section intent="body" redraft="Keep \\q." because=literal\\n}\n:::\n'
    document, findings = parse(text)
    assert not findings
    assert document.sections[0].redraft == "Keep \\q."
    assert document.sections[0].because == r"literal\n"
