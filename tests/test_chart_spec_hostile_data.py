import pytest

from ai_docs_kit.render.chart_spec import resolve_chart


def _data(values, **extra):
    return {"categories": ["a"], "series": [{"name": "s", "values": values}], **extra}


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_non_finite_values_are_unsupported_not_drawn_or_crashing(value):
    spec = resolve_chart(_data([value]))
    assert spec.type == "unsupported"


def test_null_unit_adds_no_unit_text_to_labels():
    spec = resolve_chart(_data([1], unit=None))
    assert spec.series[0].labels == ["1"]


def test_null_values_list_is_unsupported_not_a_crash():
    spec = resolve_chart(_data(None))
    assert spec.type == "unsupported"
