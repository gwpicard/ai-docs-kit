# Intent: Every chart carries a twin table of formatted values, also rendered in documents.
import importlib
import importlib.util
import json
import re
from pathlib import Path

import pytest
import yaml

from ai_docs_kit import cli
from ai_docs_kit.model import Document, Section
from ai_docs_kit.render import compose, swatch
from ai_docs_kit.source.serialiser import serialise
from ai_docs_kit.testing import golden
from ai_docs_kit.theme import neutral_theme

try:
    chart_spec = importlib.import_module("ai_docs_kit.render.chart_spec")
except ImportError as error:
    if error.name != "ai_docs_kit.render.chart_spec" and not str(error.name).startswith("ai_docs_kit.render.chart_spec."):
        raise
    if importlib.util.find_spec(error.name) is not None:
        raise
    chart_spec = None

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/components"
EXPECTED = {
    "columns": ["Region", "Current", "Previous"],
    "rows": [["North", "4", "3"], ["South", "6", "5"], ["East", "8", "6"], ["West", "5", "4"]],
}


def _section(name):
    path = FIXTURES / f"{name}.yaml"
    assert path.is_file(), f"{name} fixture must exist"
    return Section.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _doc(section, fmt):
    return Document(
        front={"doctype": "report" if fmt == "doc" else "pitch-deck", "title": "Results"},
        format=fmt,
        sections=[section],
    )


def test_D1_resolved_tables_use_formatted_labels():
    assert chart_spec is not None, "ai_docs_kit.render.chart_spec must exist"
    assert hasattr(chart_spec, "resolve_chart") and hasattr(chart_spec, "TwinTable")
    data = {**_section("chart").data, "category_label": "Region"}
    spec = chart_spec.resolve_chart(data)
    assert spec.table == chart_spec.TwinTable(**EXPECTED)
    currency = chart_spec.resolve_chart({
        "unit": "GBP", "categories": ["North", "South"],
        "series": [{"name": "Revenue", "values": [1234500, 980000.5]}],
    })
    assert currency.table == chart_spec.TwinTable(
        columns=["", "Revenue"], rows=[["North", "£1,234,500.0"], ["South", "£980,000.5"]]
    )
    unknown = chart_spec.resolve_chart({**data, "type": "unknown"})
    assert unknown.table == chart_spec.TwinTable(**EXPECTED)
    assert chart_spec.resolve_chart({}).table is None
    for resolved in (spec, currency, unknown):
        for i, row in enumerate(resolved.table.rows):
            assert row[1:] == [series.labels[i] for series in resolved.series]


def test_D2_composition_preserves_table_and_routes_formats():
    section = _section("chart")
    slide = compose.compose(_doc(section, "slides")).sections[0]
    assert slide.component == "chart"
    assert "chart" in slide.content, "chart spec must be included in composition"
    expected = {**EXPECTED, "columns": ["", "Current", "Previous"]}
    assert slide.content["chart"]["table"] == expected
    document = compose.compose(_doc(section, "doc")).sections[0]
    assert document.component == "chart-table"
    assert document.content["chart"] == slide.content["chart"]
    empty = section.model_copy(update={"data": None})
    assert compose.component_for(empty, "doc") is None
    assert compose.component_for(section, "slides") == "chart"
    assert compose.component_for(empty, "slides") == "bullets"


def test_D3_doc_table_marks_and_theme(tmp_path):
    section = _section("chart-table")
    assert section.id == "ct1"
    facts = swatch.swatch(_doc(section, "doc"), section.id, tmp_path, theme=neutral_theme()).facts
    assert len(facts.pages) == 1
    assert facts.pages[0].width == pytest.approx(595.276, abs=0.1)
    assert facts.pages[0].height == pytest.approx(841.89, abs=0.1)
    elements = [m for m in facts.marks if m.kind == "element" and m.id == section.id]
    for role, field, text in [
        ("heading", "title", "Quarterly"),
        ("table-header", "data.category_label", "Region"),
        ("table-header", "data.series[0].name", "Current"),
        ("table-header", "data.series[1].name", "Previous"),
        ("table-cell", "data.categories[0]", "North"),
        ("table-cell", "data.series[0].values[2]", "8"),
    ]:
        candidates = [m for m in elements if m.role == role and getattr(m, "field", None) == field]
        assert any(
            w.text == text and w.box.page == m.page
            and m.x <= (w.box.x0 + w.box.x1) / 2 <= m.x + m.w
            and m.y <= (w.box.y0 + w.box.y1) / 2 <= m.y + m.h
            for m in candidates for w in facts.words
        ), (role, field, text)
    figure = [m for m in elements if m.role == "figure"]
    source = [m for m in elements if m.role == "figure-source" and getattr(m, "field", None) == "source_line"]
    assert len(figure) == len(source) == 1
    assert source[0].page == figure[0].page
    assert 0 <= source[0].y - (figure[0].y + figure[0].h) <= 24
    roles = {value.upper() for value in neutral_theme().tokens.colour.roles.values()}
    assert all(w.colour is None or w.colour.upper() in roles for w in facts.words)
    assert all(s.fill is None or s.fill.upper() in roles for s in facts.shapes)
    path = ROOT / "src/ai_docs_kit/render/library/chart-table.typ"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "sec.data" not in text and 'at("data"' not in text
    assert not re.search(r"\b(?:rgb|luma|cmyk)\s*\(|#[0-9a-fA-F]{6}\b", text)


def test_D4_golden_and_check_document(tmp_path, capsys):
    section = _section("chart-table")
    path = FIXTURES / "chart-table.facts.json"
    assert path.is_file(), "chart-table golden facts must exist"
    assert golden.compare_facts(golden.facts_for("chart-table", FIXTURES), json.loads(path.read_text())) == []
    source = tmp_path / "report.md"
    source.write_text(serialise(_doc(section, "doc")), encoding="utf-8")
    try:
        code = cli.main(["check", str(source), "--out", str(tmp_path / "out")])
    except SystemExit as error:
        code = error.code
    output = capsys.readouterr()
    assert code == 0, output.out + output.err
    assert "no findings" in output.out.lower()

