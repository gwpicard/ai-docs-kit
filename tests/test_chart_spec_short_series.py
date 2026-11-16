from ai_docs_kit.render.chart_spec import resolve_chart


def test_missing_values_are_not_drawn_as_zero():
    data = {"categories": ["a", "b", "c"], "series": [{"name": "s", "values": [1]}]}
    spec = resolve_chart(data)
    assert spec.type == "unsupported" or spec.series[0].labels == ["1", "", ""]
