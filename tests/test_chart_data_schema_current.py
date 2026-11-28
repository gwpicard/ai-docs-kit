"""The published chart input schema comes from its typed model, byte for byte."""

import json
from pathlib import Path

from ai_docs_kit.render import chart_spec

COMMITTED = Path(__file__).resolve().parents[1] / "docs/schemas/chart/ChartData.schema.json"


def test_committed_chart_data_schema_matches_fresh_export(tmp_path):
    export = getattr(chart_spec, "export_chart_schema", None)
    assert callable(export), "chart_spec needs export_chart_schema(directory), following export_review_schema"
    model = getattr(chart_spec, "ChartData", None)
    assert model is not None, "ChartData must define the chart data block"

    directory = tmp_path / "nested" / "chart"
    fresh = export(directory)
    assert fresh == directory / "ChartData.schema.json"
    assert fresh.is_file(), "the exporter must write the schema into the requested directory"
    assert COMMITTED.is_file(), "publish docs/schemas/chart/ChartData.schema.json"
    assert COMMITTED.read_bytes() == fresh.read_bytes(), "regenerate the committed chart data schema"
    assert json.loads(fresh.read_text(encoding="utf-8")) == model.model_json_schema()

    # A second export replaces a stale file rather than leaving it behind.
    fresh.write_text('{"seeded": "stale schema"}\n', encoding="utf-8")
    assert export(directory) == fresh
    assert fresh.read_bytes() == COMMITTED.read_bytes()
