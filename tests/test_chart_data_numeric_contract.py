"""Authoring validation rejects coercion while chart resolution stays tolerant."""

import pytest
from pydantic import ValidationError

from ai_docs_kit.render.chart_spec import ChartData, resolve_chart


@pytest.mark.parametrize("invalid", ["12", True, None, float("inf"), float("-inf"), float("nan")])
def test_numeric_contract_pairs_valid_chart_with_invalid_value(invalid):
    valid = {
        "type": "column",
        "categories": ["Upland", "Lowland"],
        "series": [{"name": "Trips", "values": [12, -3.5]}],
    }
    parsed = ChartData.model_validate(valid)
    assert parsed.series[0].values == [12, -3.5]
    spec = resolve_chart(valid)
    assert spec.type == "column"
    assert spec.series[0].labels == ["12.0", "-3.5"]

    invalid_block = {**valid, "series": [{"name": "Trips", "values": [12, invalid]}]}
    with pytest.raises(ValidationError) as caught:
        ChartData.model_validate(invalid_block)
    assert caught.value.errors()[0]["loc"] == ("series", 0, "values", 1)
    assert resolve_chart(invalid_block).type == "unsupported"
