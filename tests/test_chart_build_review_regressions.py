"""Chart regressions through build, saved layout facts and the editable copy."""

import pytest
from pptx import Presentation

from ai_docs_kit.cli import main
from ai_docs_kit.facts.layout import LayoutFacts, centre, contains
from ai_docs_kit.model import Document, Section
from ai_docs_kit.render.marks import ElementMark
from ai_docs_kit.source.serialiser import serialise

EMU_PER_PT = 12700
SHORT = ["East", "West", "North", "South"]
LONG = "Western region revenue"


def _build(tmp_path, chart_type, categories, count=2):
    section = Section(
        id="chart",
        intent="chart",
        title="Category groups",
        data={
            "type": chart_type,
            "categories": categories,
            "series": [
                {"name": f"Series {j}", "values": [i + j + 2 for i in range(len(categories))]} for j in range(count)
            ],
        },
    )
    source = tmp_path / "deck.md"
    source.write_text(serialise(Document(front={"doctype": "pitch-deck"}, format="slides", sections=[section])))
    assert main(["build", str(source)]) == 0
    version = tmp_path / "deck.versions/v1"
    facts = LayoutFacts.model_validate_json((version / "layout.json").read_text())
    shapes = {s.name: s for s in Presentation(str(version / "deck.pptx")).slides[0].shapes}
    return facts, shapes


def _marks(facts, role):
    return [m for m in facts.marks if isinstance(m, ElementMark) and m.role == role]


def _assert_box(shape, label, rotation):
    assert shape.rotation == rotation
    width, height = shape.width / EMU_PER_PT, shape.height / EMU_PER_PT
    cx, cy = shape.left / EMU_PER_PT + width / 2, shape.top / EMU_PER_PT + height / 2
    if rotation == 90:
        width, height = height, width
    assert (cx - width / 2, cy - height / 2, width, height) == pytest.approx(
        (label.x, label.y, label.w, label.h), abs=0.01
    )


def _assert_gaps(facts, chart_type, count):
    marks = _marks(facts, "chart-mark")
    axis, size = ("y", "h") if chart_type == "bar" else ("x", "w")
    inside, between = [], []
    for i, (before, after) in enumerate(zip(marks, marks[1:], strict=False), 1):
        gap = getattr(after, axis) - getattr(before, axis) - getattr(before, size)
        (between if i % count == 0 else inside).append(gap)
    assert min(inside) > 0
    assert min(between) >= 2 * max(inside) - 0.01


@pytest.mark.parametrize("chart_type", ["bar", "column"])
def test_build_keeps_upright_multiline_letters_upright(tmp_path, chart_type):
    categories = ["A\nB\nC", *SHORT[1:]]
    facts, shapes = _build(tmp_path, chart_type, categories)
    labels = _marks(facts, "chart-label")
    shape = shapes["chart/data.categories[0]"]
    _assert_box(shape, labels[0], 0)
    assert shape.text == categories[0]
    words = [w for w in facts.words if contains(labels[0], centre(w.box))]
    assert [w.text for w in words[:3]] == ["A", "B", "C"]
    assert all(w.rotation == 0 for w in words[:3])


def test_build_mixed_columns_preserves_orientation_text_and_group_positions(tmp_path):
    categories = [SHORT[0], LONG, SHORT[2], "Southern region revenue"]
    facts, shapes = _build(tmp_path, "column", categories)
    labels = _marks(facts, "chart-label")
    marks = _marks(facts, "chart-mark")
    assert len(labels) == len(categories)
    for i, (label, rotation) in enumerate(zip(labels, [0, 90, 0, 90], strict=True)):
        assert label.field == f"data.categories[{i}]"
        shape = shapes[f"chart/{label.field}"]
        _assert_box(shape, label, rotation)
        assert shape.text == categories[i]
        group = marks[i * 2 : i * 2 + 2]
        assert label.x + label.w / 2 == pytest.approx((group[0].x + group[-1].x + group[-1].w) / 2)
        assert label.y >= max(m.y + m.h for m in group)
        words = [w for w in facts.words if contains(label, centre(w.box))]
        assert words and all(w.rotation == rotation for w in words)
    for left, right in zip(labels, labels[1:], strict=False):
        assert left.x + left.w <= right.x
    _assert_gaps(facts, "column", 2)


def test_build_wrapped_bar_words_and_short_groups_stay_upright_and_separate(tmp_path):
    categories = ["Infrastructure modernisation programme", *SHORT[1:]]
    facts, shapes = _build(tmp_path, "bar", categories)
    labels = _marks(facts, "chart-label")
    wrapped = shapes["chart/data.categories[0]"]
    assert len(wrapped.text.splitlines()) > 1
    assert " ".join(wrapped.text.split()) == categories[0]
    assert labels[0].y >= _marks(facts, "chart-plot")[0].y
    for label in labels:
        _assert_box(shapes[f"chart/{label.field}"], label, 0)
    _assert_gaps(facts, "bar", 2)


@pytest.mark.parametrize("chart_type", ["bar", "column"])
@pytest.mark.parametrize("count,categories", [(2, SHORT), (3, [*SHORT, "Upper", "Lower"])], ids=["pairs", "many"])
def test_build_short_groups_have_separate_bars_and_upright_labels(tmp_path, chart_type, count, categories):
    facts, shapes = _build(tmp_path, chart_type, categories, count)
    assert len(_marks(facts, "chart-mark")) == count * len(categories)
    _assert_gaps(facts, chart_type, count)
    labels = _marks(facts, "chart-label")
    assert len(labels) == len(categories)
    for i, label in enumerate(labels):
        shape = shapes[f"chart/data.categories[{i}]"]
        _assert_box(shape, label, 0)
        assert shape.text == categories[i]
