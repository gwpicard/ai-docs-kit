"""A wrapped bar label stays upright in the PowerPoint copy; charts of over eight bars separate groups."""

import pytest
from pptx import Presentation

from ai_docs_kit.facts.layout import PlacedWord
from ai_docs_kit.model import Document, Section
from ai_docs_kit.render import swatch
from ai_docs_kit.render.marks import ElementMark
from ai_docs_kit.render.pptx_copy import _add_box
from ai_docs_kit.theme import neutral_theme


def _word(text, y):
    box = {"page": 1, "x0": 40.0, "y0": y, "x1": 40.0 + 7 * len(text), "y1": y + 14.0}
    return PlacedWord(
        text=text, font="Inter", size=14.0, colour=None, box=box, baseline=y + 11, role="title", section_id="s"
    )


def _rotation_of(words):
    slide = Presentation().slides.add_slide(Presentation().slide_layouts[6])
    _add_box(slide, "s/title", words, (40.0, 100.0, 120.0, 34.0))
    return slide.shapes[0].rotation % 360


def test_text_wrapped_to_one_word_per_line_stays_upright_in_the_pptx():
    words = [_word("Infrastructure", 100.0), _word("modernisation", 114.0)]
    assert _rotation_of(words) == 0


def test_letters_stacked_in_one_column_are_a_turned_label():
    words = [_word(letter, 100.0 + 10 * i) for i, letter in enumerate("East")]
    assert _rotation_of(words) == 90


@pytest.mark.parametrize("chart_type", ["bar", "column"])
def test_many_bars_still_separate_groups(chart_type, tmp_path):
    categories = [f"C{i}" for i in range(6)]
    series = [{"name": n, "values": [3, 4, 5, 2, 6, 4]} for n in ("a", "b", "c")]
    data = {"categories": categories, "series": series, "type": chart_type}
    doc = Document(
        front={"doctype": "pitch-deck", "title": "Charts"},
        format="slides",
        sections=[Section(id="s1", intent="chart", title="Groups", data=data)],
    )
    facts = swatch.swatch(doc, "s1", tmp_path, theme=neutral_theme()).facts
    marks = [m for m in facts.marks if isinstance(m, ElementMark) and m.role == "chart-mark"]
    start, size = ("y", "h") if chart_type == "bar" else ("x", "w")
    inside, between = [], []
    for i in range(1, len(marks)):
        gap = getattr(marks[i], start) - (getattr(marks[i - 1], start) + getattr(marks[i - 1], size))
        (between if i % 3 == 0 else inside).append(gap)
    assert min(between) >= 2 * max(inside) - 0.01, (inside, between)
