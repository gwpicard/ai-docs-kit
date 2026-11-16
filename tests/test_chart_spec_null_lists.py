import pytest

from ai_docs_kit.render.chart_spec import resolve_chart


@pytest.mark.parametrize(
    "data",
    [{"categories": None, "series": []}, {"categories": ["a"], "series": None}],
)
def test_null_categories_or_series_are_unsupported_not_a_crash(data):
    assert resolve_chart(data).type == "unsupported"
