from ai_docs_kit.render.chart_spec import resolve_chart


def test_scale_minimum_covers_negative_values():
    data = {"categories": ["a", "b"], "series": [{"name": "s", "values": [-5, 3]}]}
    spec = resolve_chart(data)
    assert spec.scale.min <= -5
