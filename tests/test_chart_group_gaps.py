"""Multi-series bar and column charts separate the category groups and keep short column labels horizontal."""

import pytest
from pptx import Presentation

from ai_docs_kit.cli import main
from ai_docs_kit.facts.layout import LayoutFacts
from ai_docs_kit.model import Document, Section
from ai_docs_kit.render import swatch
from ai_docs_kit.render.marks import ElementMark
from ai_docs_kit.theme import neutral_theme

EMU_PER_PT = 12700
SHORT = ["East", "West", "North", "South"]
LONG = ["Eastern region revenue", "Western region revenue", "Northern region revenue", "Southern region revenue"]
SERIES = [{"name": "2024", "values": [4, 6, 5, 3]}, {"name": "2025", "values": [5, 7, 6, 4]}]


def _data(chart_type, categories):
    return {"categories": categories, "series": SERIES, "type": chart_type}


def _facts(chart_type, categories, tmp_path) -> LayoutFacts:
    section = Section(id="s1", intent="chart", title="Groups", data=_data(chart_type, categories))
    doc = Document(front={"doctype": "pitch-deck", "title": "Charts"}, format="slides", sections=[section])
    return swatch.swatch(doc, "s1", tmp_path, theme=neutral_theme()).facts


def _marks(facts, role):
    return [m for m in facts.marks if isinstance(m, ElementMark) and m.role == role]


def _gaps(facts, chart_type, categories):
    """Return the gaps between neighbouring bars inside a group and between neighbouring groups."""
    marks = _marks(facts, "chart-mark")
    count = len(SERIES)
    assert len(marks) == len(categories) * count
    start, size = ("y", "h") if chart_type == "bar" else ("x", "w")
    inside, between = [], []
    for i in range(1, len(marks)):
        previous, current = marks[i - 1], marks[i]
        gap = getattr(current, start) - (getattr(previous, start) + getattr(previous, size))
        (between if i % count == 0 else inside).append(gap)
    return inside, between


@pytest.mark.parametrize("chart_type", ["bar", "column"])
@pytest.mark.parametrize("categories", [SHORT, LONG], ids=["short", "long"])
def test_gap_between_groups_is_at_least_twice_the_gap_inside_a_group(chart_type, categories, tmp_path):
    inside, between = _gaps(_facts(chart_type, categories, tmp_path), chart_type, categories)
    assert inside and between
    assert min(between) >= 2 * max(inside) - 0.01, (inside, between)
    assert min(between) > 0


def _is_horizontal(label: ElementMark) -> bool:
    return label.w >= label.h


def _slot(facts, categories):
    labels = _marks(facts, "chart-label")
    assert len(labels) == len(categories)
    return labels


def test_short_column_labels_are_horizontal(tmp_path):
    facts = _facts("column", SHORT, tmp_path)
    labels = _slot(facts, SHORT)
    assert all(_is_horizontal(label) for label in labels), [(m.w, m.h) for m in labels]


def test_long_column_labels_are_rotated_and_do_not_overlap(tmp_path):
    facts = _facts("column", LONG, tmp_path)
    labels = _slot(facts, LONG)
    assert not any(_is_horizontal(label) for label in labels), [(m.w, m.h) for m in labels]
    ordered = sorted(labels, key=lambda m: m.x)
    for left, right in zip(ordered, ordered[1:], strict=False):
        assert left.x + left.w <= right.x + 0.01


def test_horizontal_column_labels_sit_under_their_group_and_do_not_overlap(tmp_path):
    facts = _facts("column", SHORT, tmp_path)
    labels = sorted(_slot(facts, SHORT), key=lambda m: m.x)
    marks = _marks(facts, "chart-mark")
    for i, label in enumerate(labels):
        group = marks[i * 2 : i * 2 + 2]
        left, right = group[0].x, group[-1].x + group[-1].w
        assert left - 0.5 <= label.x + label.w / 2 <= right + 0.5
        assert label.y >= max(m.y + m.h for m in group) - 0.5
    for left, right in zip(labels, labels[1:], strict=False):
        assert left.x + left.w <= right.x


CHART_DECK = """---
doctype: pitch-deck
format: slides
title: Readout
---

## Sources

- [S1] Illustrative deck content

::: {{#chart intent=chart}}
## Groups
```data
type: column
categories: {categories}
series:
  - name: "2024"
    values: [4, 6, 5, 3]
  - name: "2025"
    values: [5, 7, 6, 4]
```
:::
"""


@pytest.mark.parametrize("categories", [SHORT, LONG], ids=["short", "long"])
def test_pptx_category_labels_are_named_and_rotated_like_the_pdf(tmp_path, categories):
    file = tmp_path / "deck.md"
    file.write_text(CHART_DECK.format(categories=categories), encoding="utf-8")
    assert main(["build", str(file)]) == 0
    version = tmp_path / "deck.versions" / "v1"
    facts = LayoutFacts.model_validate_json((version / "layout.json").read_text(encoding="utf-8"))
    labels = _slot(facts, categories)
    shapes = {s.name: s for slide in Presentation(str(version / "deck.pptx")).slides for s in slide.shapes}
    for label in labels:
        shape = shapes[f"{label.id}/{label.field}"]
        centre_x = (shape.left + shape.width / 2) / EMU_PER_PT
        centre_y = (shape.top + shape.height / 2) / EMU_PER_PT
        assert centre_x == pytest.approx(label.x + label.w / 2, abs=1.5), shape.name
        assert centre_y == pytest.approx(label.y + label.h / 2, abs=1.5), shape.name
        turned = shape.rotation % 360 not in (0, 180)
        assert turned == (not _is_horizontal(label)), shape.name
