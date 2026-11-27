"""Document charts draw resolved data through the build and check commands."""

import json
import shutil
from collections import Counter
from pathlib import Path

import pytest
import yaml

from ai_docs_kit.cli import main
from ai_docs_kit.facts.layout import LayoutFacts
from ai_docs_kit.model import Document, Section
from ai_docs_kit.render.chart_spec import resolve_chart
from ai_docs_kit.render.components import all_manifests
from ai_docs_kit.render.marks import ElementMark
from ai_docs_kit.source.serialiser import serialise
from ai_docs_kit.testing.golden import compare_facts, facts_for

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/components"


def _fixture():
    return Section.model_validate(yaml.safe_load((FIXTURES / "doc-chart.yaml").read_text(encoding="utf-8")))


def _run(args, capsys):
    code = main(args)
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def _build(tmp_path, capsys, *sections):
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "report.md"
    source.write_text(serialise(Document(front={}, format="doc", sections=list(sections))), encoding="utf-8")
    code, output = _run(["build", str(source)], capsys)
    assert code == 0, output
    version = tmp_path / "report.versions/v1"
    assert (version / "report.pdf").is_file(), output
    facts = LayoutFacts.model_validate_json((version / "layout.json").read_text(encoding="utf-8"))
    composition = json.loads((version / "composition.json").read_text(encoding="utf-8"))
    findings = json.loads((version / "findings.json").read_text(encoding="utf-8"))
    return facts, composition["sections"], findings


def _marks(facts, section, role):
    return [mark for mark in facts.marks if isinstance(mark, ElementMark) and mark.id == section and mark.role == role]


def _text(facts, mark):
    words = [
        word.text
        for word in facts.words
        if word.box.page == mark.page
        and mark.x - 0.1 <= (word.box.x0 + word.box.x1) / 2 <= mark.x + mark.w + 0.1
        and mark.y - 0.1 <= (word.box.y0 + word.box.y1) / 2 <= mark.y + mark.h + 0.1
    ]
    return "".join("".join(words).split())


def _assert_drawn(facts, section, spec):
    marks = _marks(facts, section.id, "chart-mark")
    expected = {
        f"data.series[{j}].values[{i}]": value
        for j, series in enumerate(spec.series)
        for i, value in enumerate(series.values)
    }
    assert Counter(mark.field for mark in marks) == Counter(dict.fromkeys(expected, 1)), (
        "The document must draw one chart-mark for each value, with the slide chart's field paths"
    )
    shapes = [shape for shape in facts.shapes if shape.section_id == section.id and shape.role == "chart-mark"]
    assert len(shapes) == len(expected), "Semantic marks must describe shapes drawn in the PDF"
    assert all(shape.fill is not None for shape in shapes)
    dimension = "w" if spec.type == "bar" else "h"
    ratios = [getattr(mark, dimension) / abs(expected[mark.field]) for mark in marks]
    assert min(ratios) > 0
    assert ratios == pytest.approx([ratios[0]] * len(ratios), abs=0.02)
    labels = _marks(facts, section.id, "chart-label")
    assert Counter(mark.field for mark in labels) == Counter(
        {f"data.categories[{i}]": 1 for i in range(len(spec.categories))}
    )
    for i, category in enumerate(spec.categories):
        label = next(mark for mark in labels if mark.field == f"data.categories[{i}]")
        assert "".join(category.split()) in _text(facts, label)
    legends = _marks(facts, section.id, "chart-legend")
    assert legends, "Several series need a legend"
    legend_text = "".join(_text(facts, legend) for legend in legends)
    assert all("".join(series.name.split()) in legend_text for series in spec.series)
    for mark in [*marks, *labels, *legends]:
        page = next(page for page in facts.pages if page.page == mark.page)
        assert 0 <= mark.x < mark.x + mark.w <= page.width + 0.1
        assert 0 <= mark.y < mark.y + mark.h <= page.height + 0.1


@pytest.mark.parametrize("requested", [True, False], ids=["explicit", "resolved"])
@pytest.mark.parametrize("kind", ["bar", "column"])
def test_build_draws_doc_charts_and_preserves_resolved_twin_table(tmp_path, capsys, kind, requested):
    section = _fixture()
    if kind == "bar":
        section.data["categories"] = ["Upland", "Lowland", "Riverside", "Hilltop", "Old quay", "Meadow"]
        for series in section.data["series"]:
            series["values"] = series["values"][:6]
    section.data["type"] = kind
    if not requested:
        del section.data["type"]
    spec = resolve_chart(section.data)
    assert spec.type == kind
    facts, sections, findings = _build(tmp_path, capsys, section)
    _assert_drawn(facts, section, spec)
    chosen = sections[0]
    assert chosen["component"] not in {"chart", "chart-table"}
    assert all_manifests()[chosen["component"]].format == "doc"
    assert chosen["content"]["chart"] == spec.model_dump(mode="json")
    table = chosen["content"]["chart"]["table"]
    assert table["columns"] == [section.data["category_label"], *(s.name for s in spec.series)]
    assert table["rows"] == [
        [category, *(series.labels[i] for series in spec.series)] for i, category in enumerate(spec.categories)
    ]
    assert not [finding for finding in findings if finding["rule_id"] == "data.values-visible"]
    assert len(facts.pages) == 1
    assert facts.pages[0].width == pytest.approx(595.276, abs=0.1)
    assert facts.pages[0].height == pytest.approx(841.89, abs=0.1)


def test_doc_chart_capacity_draws_twenty_four_categories_and_five_series(tmp_path, capsys):
    section = _fixture()
    section.data["categories"] = [f"Month {i + 1:02}" for i in range(24)]
    section.data["series"] = [
        {"name": name, "values": [(i + 1) * (j + 1) for i in range(24)]}
        for j, name in enumerate(["Upland", "Lowland", "Riverside", "Hilltop", "Meadow"])
    ]
    facts, sections, findings = _build(tmp_path, capsys, section)
    _assert_drawn(facts, section, resolve_chart(section.data))
    manifest = all_manifests()[sections[0]["component"]]
    assert manifest.capacity["categories"][1] >= 24
    assert manifest.capacity["series"][1] >= 5
    assert not [finding for finding in findings if finding["rule_id"] in {"source.capacity", "data.values-visible"}]
    assert len(facts.pages) == 1


@pytest.mark.parametrize("reverse", [False, True], ids=["fallback-first", "drawable-first"])
def test_unsupported_pie_stays_a_table_beside_a_drawable_chart(tmp_path, capsys, reverse):
    drawn = _fixture()
    drawn.data["categories"] = drawn.data["categories"][:2]
    for series in drawn.data["series"]:
        series["values"] = series["values"][:2]
    fallback = drawn.model_copy(deep=True, update={"id": "unsupported"})
    fallback.data.update({"type": "pie", "unit": "GBP"})
    spec = resolve_chart(fallback.data)
    assert spec.type == "unsupported"
    ordered = [drawn, fallback] if reverse else [fallback, drawn]
    facts, sections, findings = _build(tmp_path, capsys, *ordered)
    by_id = {section["id"]: section for section in sections}
    assert by_id[fallback.id]["component"] == "chart-table"
    assert by_id[fallback.id]["content"]["chart"] == spec.model_dump(mode="json")
    assert _marks(facts, fallback.id, "chart-mark") == []
    cells = _marks(facts, fallback.id, "table-cell")
    for i, row in enumerate(spec.table.rows):
        for j, value in enumerate(row):
            field = f"data.categories[{i}]" if j == 0 else f"data.series[{j - 1}].values[{i}]"
            assert any(mark.field == field and value in _text(facts, mark) for mark in cells), (field, value)
    assert not [finding for finding in findings if finding["rule_id"] == "data.values-visible"]
    _assert_drawn(facts, drawn, resolve_chart(drawn.data))


@pytest.mark.parametrize("order", ["prose-first", "data-first"])
def test_doc_chart_keeps_prose_and_source_in_working_file_order(tmp_path, capsys, order):
    section = _fixture()
    if order == "data-first":
        section.content_order = ["data", "paragraphs[0]", "paragraphs[1]"]
    facts, _, findings = _build(tmp_path, capsys, section)
    chart = _marks(facts, section.id, "chart-plot")
    assert len(chart) == 1, "The new document component must draw a chart plot"
    paragraphs = []
    for i, paragraph in enumerate(section.paragraphs):
        candidates = [
            mark
            for mark in facts.marks
            if isinstance(mark, ElementMark) and mark.id == section.id and mark.field == f"paragraphs[{i}]"
        ]
        assert len(candidates) == 1
        assert "".join(paragraph.split()) in _text(facts, candidates[0])
        paragraphs.append(candidates[0])
    reading_order = [*paragraphs, chart[0]] if order == "prose-first" else [chart[0], *paragraphs]
    for before, after in zip(reading_order, reading_order[1:], strict=False):
        assert before.page == after.page
        assert before.y + before.h <= after.y + 0.1
    sources = _marks(facts, section.id, "figure-source")
    assert len(sources) == 1 and sources[0].field == "source_line"
    assert "".join(section.source_line.split()) in _text(facts, sources[0])
    assert all(mark.page == sources[0].page and mark.y + mark.h <= sources[0].y + 0.1 for mark in reading_order)
    assert not [finding for finding in findings if finding["rule_id"] == "geo.text-present"]


def _outline_source(tmp_path, intent="chart"):
    source = tmp_path / f"{intent}.md"
    doc = Document(
        front={"doctype": "report"},
        format="doc",
        sections=[
            Section(id="intro", section="introduction", intent="body", title="Scope", paragraphs=["Survey scope."]),
            Section(id="pending", section="content", intent=intent, title="Monthly trips"),
            Section(id="end", section="findings", intent="callout", title="Next steps", paragraphs=["Survey again."]),
        ],
    )
    source.write_text(serialise(doc), encoding="utf-8")
    return source


def test_outline_defers_missing_chart_data_but_keeps_unknown_intent_errors(tmp_path, capsys):
    unknown = _outline_source(tmp_path, "unknown")
    code, output = _run(["check", str(unknown), "--outline", "--out", str(tmp_path / "unknown-out")], capsys)
    assert code == 1 and "source.intent-known" in output, output
    source = _outline_source(tmp_path)
    code, output = _run(["check", str(source), "--out", str(tmp_path / "full")], capsys)
    assert code == 1 and "source.intent-known" in output, output
    code, output = _run(["check", str(source), "--outline", "--out", str(tmp_path / "outline")], capsys)
    assert code == 0, output
    assert "source.intent-known" not in output
    report = json.loads((tmp_path / "outline/chart.findings.json").read_text(encoding="utf-8"))
    assert not [finding for finding in report if finding["rule_id"] == "source.intent-known"]


def test_build_still_reports_intent_known_for_a_doc_chart_without_data(tmp_path, capsys):
    source = _outline_source(tmp_path)
    code, output = _run(["check", str(source), "--out", str(tmp_path / "full")], capsys)
    assert code == 1 and "source.intent-known" in output, output
    code, output = _run(["build", str(source)], capsys)
    assert code != 0, "A full build must refuse a document chart without data"
    assert "source.intent-known" in output, output
    assert not (tmp_path / "chart.versions/v1").exists()


def test_new_doc_chart_component_has_a_fixture_and_generated_golden(tmp_path, capsys):
    _, sections, _ = _build(tmp_path / "build", capsys, _fixture())
    component = sections[0]["component"]
    assert component not in {"chart", "chart-table"}, "A new document chart component needs its own golden"
    manifest = all_manifests()[component]
    assert manifest.format == "doc" and manifest.fixture
    fixture = ROOT / manifest.fixture
    assert fixture.is_file(), "Ship a component fixture beside its golden facts"
    golden = fixture.with_suffix(".facts.json")
    assert golden.is_file(), "Generate the new golden with scripts/golden_facts.py after implementing the component"
    fixture_section = Section.model_validate(yaml.safe_load(fixture.read_text(encoding="utf-8")))
    assert resolve_chart(fixture_section.data).type in {"bar", "column"}
    scratch = tmp_path / "golden"
    scratch.mkdir()
    shutil.copyfile(fixture, scratch / f"{component}.yaml")
    expected = json.loads(golden.read_text(encoding="utf-8"))
    assert expected.get("chart-mark", {}).get("marks"), "The golden must record drawn chart marks"
    assert compare_facts(facts_for(component, scratch), expected) == []
