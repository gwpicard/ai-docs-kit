"""Rotated chart labels keep the PDF's font size and lines in the editable copy."""

import pytest

from ai_docs_kit.facts.layout import centre, contains
from test_chart_build_review_regressions import _assert_box, _build, _marks


@pytest.mark.parametrize("text", ["Infrastructure progress", "Southern region revenue"])
def test_build_keeps_rotated_label_font_size(tmp_path, text):
    facts, shapes = _build(tmp_path, "column", ["East", text, "North", "South"])
    labels = _marks(facts, "chart-label")
    for i, label in enumerate(labels):
        shape = shapes[f"chart/data.categories[{i}]"]
        _assert_box(shape, label, 90 if i == 1 else 0)
        words = [word for word in facts.words if contains(label, centre(word.box))]
        assert words and all(word.size == pytest.approx(18, abs=0.01) for word in words)
        runs = [run for paragraph in shape.text_frame.paragraphs for run in paragraph.runs]
        assert runs and all(run.font.size.pt == pytest.approx(18, abs=0.01) for run in runs)


@pytest.mark.parametrize(
    "text",
    [
        "Western region revenue\nSecond line",
        "First line\nWestern region revenue",
        "Western region revenue\nSecond line\nThird line",
    ],
    ids=["long-first", "long-second", "three-lines"],
)
def test_build_keeps_rotated_label_lines_in_reading_order(tmp_path, text):
    facts, shapes = _build(tmp_path, "column", ["East", text, "North", "South"])
    labels = _marks(facts, "chart-label")
    shape = shapes["chart/data.categories[1]"]
    _assert_box(shape, labels[1], 90)
    assert [paragraph.text for paragraph in shape.text_frame.paragraphs] == text.splitlines()
    assert shape.text == text
    assert shapes["chart/data.categories[0]"].text == "East"
    assert shapes["chart/data.categories[0]"].rotation == 0
