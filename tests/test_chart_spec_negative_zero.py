from ai_docs_kit.render.chart_spec import format_value, resolve_chart


def test_value_rounding_to_zero_has_no_minus_sign():
    assert format_value(-0.0004, 3, None) == "0.000"
    assert format_value(-0.0, 0, "GBP") == "£0"


def test_chart_labels_of_negative_zero_have_no_minus_sign():
    data = {"categories": ["a"], "series": [{"name": "s", "values": [-0.0]}], "unit": "GBP"}
    assert resolve_chart(data).series[0].labels == ["£0"]
