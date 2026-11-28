"""Judge chart inputs through the published model and the resolver that consumes it."""

import json
import re
from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from pydantic import BaseModel, ValidationError, model_validator

from ai_docs_kit.render import chart_spec

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "docs/schemas/chart/ChartData.schema.json"
REFERENCE = ROOT / "skills/create/working-file.md"
DATA_BLOCK = re.compile(r"^```data\s*\n(.*?)^```\s*$", re.MULTILINE | re.DOTALL)
FIELDS = {"type", "categories", "series", "unit", "category_label", "time_series", "ordered"}


def _model():
    model = getattr(chart_spec, "ChartData", None)
    assert isinstance(model, type) and issubclass(model, BaseModel), "chart_spec needs a typed ChartData input model"
    return model


def _schema():
    assert SCHEMA.is_file(), "publish docs/schemas/chart/ChartData.schema.json"
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def _data(**extra):
    return {
        "categories": ["Upland", "Lowland"],
        "series": [{"name": "Trips", "values": [12, -3.5]}, {"name": "Visits", "values": [4.5, 9]}],
        **extra,
    }


def _chart_blocks(text):
    for index, match in enumerate(DATA_BLOCK.finditer(text), 1):
        data = yaml.safe_load(match[1])
        if isinstance(data, dict) and ("categories" in data or "series" in data):
            yield index, data


def _resolve_schema(node, schema):
    while "$ref" in node:
        assert node["$ref"].startswith("#/"), "chart data schema references must be self-contained"
        target = schema
        for part in node["$ref"][2:].split("/"):
            target = target[part.replace("~1", "/").replace("~0", "~")]
        node = target
    return node


def _branches(node, schema):
    node = _resolve_schema(node, schema)
    return [_resolve_schema(branch, schema) for branch in node.get("anyOf", [node])]


def test_chart_data_schema_describes_typed_input_fields_and_nested_series():
    model = _model()
    schema = _schema()
    assert schema == model.model_json_schema(), "the published schema must describe the input model"
    properties = schema["properties"]
    assert FIELDS <= properties.keys()
    categories = _resolve_schema(properties["categories"], schema)
    assert categories["type"] == "array" and categories["items"]["type"] == "string"
    series = _resolve_schema(properties["series"], schema)
    assert series["type"] == "array"
    item = _resolve_schema(series["items"], schema)
    assert item["type"] == "object"
    assert item["properties"]["name"]["type"] == "string"
    values = _resolve_schema(item["properties"]["values"], schema)
    assert values["type"] == "array"
    assert {branch.get("type") for branch in _branches(values["items"], schema)} <= {"integer", "number"}
    for field, expected in (
        ("unit", "string"),
        ("category_label", "string"),
        ("time_series", "boolean"),
        ("ordered", "boolean"),
    ):
        assert expected in {branch.get("type") for branch in _branches(properties[field], schema)}, field
    allowed_types = {value for branch in _branches(properties["type"], schema) for value in branch.get("enum", [])}
    assert {"bar", "column", "line", "pie"} <= allowed_types, (
        "include drawn types and the chart-table fixture's fallback"
    )
    assert "unknown-chart-kind" not in allowed_types


@pytest.mark.parametrize("source", ["fixtures", "reference"])
def test_every_chart_example_validates_through_the_published_model(source):
    model = _model()
    assert _schema() == model.model_json_schema()
    examples = []
    if source == "fixtures":
        for path in sorted((ROOT / "tests/fixtures").rglob("*.yaml")):
            fixture = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(fixture, dict) and fixture.get("intent") == "chart" and "data" in fixture:
                examples.append((str(path.relative_to(ROOT)), fixture["data"]))
        for path in sorted((ROOT / "tests/fixtures").rglob("*.md")):
            examples.extend(
                (f"{path.relative_to(ROOT)}:data block {index}", data)
                for index, data in _chart_blocks(path.read_text(encoding="utf-8"))
            )
        names = {name for name, _ in examples}
        assert {
            f"tests/fixtures/components/{name}.yaml" for name in ("chart", "chart-table", "doc-chart", "doc-chart-line")
        } <= names
    else:
        examples = [
            (f"reference:data block {index}", data)
            for index, data in _chart_blocks(REFERENCE.read_text(encoding="utf-8"))
        ]
    assert examples, f"{source} must contain chart data examples"
    for location, data in examples:
        try:
            validated = model.model_validate(data)
        except ValidationError as error:
            pytest.fail(f"{location} does not validate as ChartData: {error}")
        assert validated.categories == data["categories"], location
        assert [series.values for series in validated.series] == [series["values"] for series in data["series"]], (
            location
        )


@pytest.mark.parametrize("defect", ["non-numeric-value", "unknown-type"])
@pytest.mark.parametrize("reverse", [False, True], ids=["forward", "reversed"])
def test_model_refuses_invalid_blocks_but_resolver_remains_tolerant(defect, reverse):
    model = _model()
    valid = _data(type="line", unit="%", category_label="Zone", time_series=False, ordered=True)
    if reverse:
        valid["categories"].reverse()
        valid["series"].reverse()
        for series in valid["series"]:
            series["values"].reverse()
        valid = dict(reversed(list(valid.items())))
    parsed = model.model_validate(valid)
    assert parsed.model_dump(include=FIELDS) == valid
    assert chart_spec.resolve_chart(valid).type == "line"

    invalid = deepcopy(valid)
    if defect == "non-numeric-value":
        invalid["series"][-1]["values"][-1] = "not-a-number"
        expected_location = ("series", 1, "values", 1)
    else:
        invalid["type"] = "unknown-chart-kind"
        expected_location = ("type",)
    with pytest.raises(ValidationError) as caught:
        model.model_validate(invalid)
    assert any(error["loc"][: len(expected_location)] == expected_location for error in caught.value.errors())
    assert chart_spec.resolve_chart(invalid).type == "unsupported"

    hostile_blocks = [
        None,
        {},
        {"categories": None, "series": []},
        {"categories": ["Upland"], "series": None},
    ]
    hostile_blocks.extend(
        {"categories": ["Upland"], "series": [{"name": "Trips", "values": values}]}
        for values in (None, "twelve", 12, {"first": 12}, [None], [float("inf")])
    )
    for hostile in hostile_blocks:
        assert chart_spec.resolve_chart(hostile).type == "unsupported", hostile
    short = chart_spec.resolve_chart({"categories": ["A", "B", "C"], "series": [{"name": "Trips", "values": [3]}]})
    assert short.type == "unsupported" or short.series[0].labels == ["3", "", ""]


@pytest.mark.parametrize(
    "extra, expected", [({"ordered": True}, "column"), ({"time_series": True}, "column"), ({"type": "line"}, "line")]
)
def test_resolve_chart_reads_the_validated_model(monkeypatch, extra, expected):
    model = _model()
    seen = []

    class ObservedChartData(model):
        @model_validator(mode="after")
        def record_validation(self):
            seen.append(self.categories)
            # The table heading proves resolution consumes the validated result.
            object.__setattr__(self, "category_label", "Validated zone")
            return self

    monkeypatch.setattr(chart_spec, "ChartData", ObservedChartData)
    data = _data(category_label="Original zone", **extra)
    before = deepcopy(data)
    spec = chart_spec.resolve_chart(data)
    assert seen, "resolve_chart must read its input through ChartData"
    assert seen[-1] == data["categories"]
    assert spec.type == expected
    assert spec.categories == data["categories"]
    assert [series.values for series in spec.series] == [series["values"] for series in data["series"]]
    assert spec.table is not None and spec.table.columns == ["Validated zone", "Trips", "Visits"]
    assert data == before, "resolving a chart must not rewrite the caller's data block"
