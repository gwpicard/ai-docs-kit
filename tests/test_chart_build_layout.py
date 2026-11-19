"""Saved chart facts and editable labels agree with the category groups on the page."""

import pytest
from pptx import Presentation

from ai_docs_kit.cli import main
from ai_docs_kit.facts.layout import LayoutFacts
from ai_docs_kit.model import Document, Section
from ai_docs_kit.render.marks import ElementMark
from ai_docs_kit.source.serialiser import serialise

EMU_PER_PT = 12700
SHORT = ["East", "West", "North", "South"]
LONG = ["Eastern region revenue", "Western region revenue", "Northern region revenue", "Southern region revenue"]


def _build(tmp_path, chart_type, categories):
    doc = Document(
        front={"doctype": "pitch-deck", "title": "Chart groups"},
        format="slides",
        sections=[
            Section(
                id="chart",
                intent="chart",
                title="Groups",
                data={
                    "type": chart_type,
                    "categories": categories,
                    "series": [
                        {"name": "Current", "values": [4, 6, 5, 3]},
                        {"name": "Previous", "values": [5, 7, 6, 4]},
                    ],
                },
            )
        ],
    )
    source = tmp_path / "deck.md"
    source.write_text(serialise(doc), encoding="utf-8")
    assert main(["build", str(source)]) == 0
    version = tmp_path / "deck.versions" / "v1"
    facts = LayoutFacts.model_validate_json((version / "layout.json").read_text(encoding="utf-8"))
    return facts, Presentation(str(version / "deck.pptx"))


def _marks(facts, role):
    return [mark for mark in facts.marks if isinstance(mark, ElementMark) and mark.role == role]


@pytest.mark.parametrize("chart_type", ["bar", "column"])
@pytest.mark.parametrize("categories", [SHORT, LONG], ids=["short", "long"])
def test_saved_layout_separates_category_groups(tmp_path, chart_type, categories):
    facts, _ = _build(tmp_path, chart_type, categories)
    marks = _marks(facts, "chart-mark")
    assert len(marks) == 2 * len(categories)
    axis, size = ("y", "h") if chart_type == "bar" else ("x", "w")
    inside, between = [], []
    for i, (before, after) in enumerate(zip(marks, marks[1:], strict=False), 1):
        gap = getattr(after, axis) - getattr(before, axis) - getattr(before, size)
        (between if i % 2 == 0 else inside).append(gap)
    assert min(inside) > 0
    assert min(between) >= 2 * max(inside) - 0.01
    if chart_type == "column":
        assert all((label.w >= label.h) == (categories == SHORT) for label in _marks(facts, "chart-label"))


def test_mixed_column_labels_turn_only_the_labels_that_do_not_fit(tmp_path):
    categories = [SHORT[0], LONG[1], SHORT[2], LONG[3]]
    facts, deck = _build(tmp_path, "column", categories)
    labels = _marks(facts, "chart-label")
    assert [label.field for label in labels] == [f"data.categories[{i}]" for i in range(len(categories))]
    assert [label.w < label.h for label in labels] == [False, True, False, True]
    shapes = {shape.name: shape for shape in deck.slides[0].shapes}
    for i, label in enumerate(labels):
        shape = shapes[f"chart/data.categories[{i}]"]
        assert shape.text == categories[i]
        turned = shape.rotation == 90
        assert turned == (label.w < label.h)
        width, height = shape.width / EMU_PER_PT, shape.height / EMU_PER_PT
        centre_x = shape.left / EMU_PER_PT + width / 2
        centre_y = shape.top / EMU_PER_PT + height / 2
        if turned:
            width, height = height, width
        assert (centre_x - width / 2, centre_y - height / 2, width, height) == pytest.approx(
            (label.x, label.y, label.w, label.h), abs=0.01
        )
    for left, right in zip(labels, labels[1:], strict=False):
        assert left.x + left.w <= right.x
