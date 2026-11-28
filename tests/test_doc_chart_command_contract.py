"""Judge document chart capacity, mixed content and outline deferral through commands.

The existing chart build judges cover the fixture and its generated golden.
These cases cover both orientations at capacity and PLAN.md's reading order.
"""

import json
from collections import Counter

import pytest
import yaml

from ai_docs_kit.cli import main
from ai_docs_kit.facts.layout import LayoutFacts
from ai_docs_kit.render.chart_spec import resolve_chart
from ai_docs_kit.render.components import all_manifests
from ai_docs_kit.render.marks import ElementMark
from ai_docs_kit.theme import neutral_theme

FRONT = "---\ndoctype: report\nformat: doc\n---\n\n"
PROSE = ["The zones follow different seasonal patterns.", "Keep the survey limits beside the recommendation."]
SOURCE = "Source: Synthetic survey register"


def _section(ident, intent, blocks, section="content"):
    return f'::: {{#{ident} .section intent="{intent}" section="{section}"}}\n' + "\n\n".join(blocks) + "\n:::\n\n"


def _data_block(data):
    return "```data\n" + yaml.safe_dump(data, sort_keys=False) + "```"


def _run(capsys, *args):
    code = main(list(map(str, args)))
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def _build(source, capsys):
    code, output = _run(capsys, "build", source)
    assert code == 0, output
    version = source.parent / f"{source.stem}.versions/v1"
    assert (version / f"{source.stem}.pdf").is_file(), output
    facts = LayoutFacts.model_validate_json((version / "layout.json").read_bytes())
    composition = json.loads((version / "composition.json").read_bytes())
    findings = json.loads((version / "findings.json").read_bytes())
    return facts, composition["sections"], findings


def _marks(facts, ident, role):
    return [mark for mark in facts.marks if isinstance(mark, ElementMark) and mark.id == ident and mark.role == role]


def _text(facts, mark):
    return "".join(
        word.text
        for word in facts.words
        if word.box.page == mark.page
        and mark.x - 0.1 <= (word.box.x0 + word.box.x1) / 2 <= mark.x + mark.w + 0.1
        and mark.y - 0.1 <= (word.box.y0 + word.box.y1) / 2 <= mark.y + mark.h + 0.1
    ).replace(" ", "")


def _before(first, second):
    assert first.page < second.page or (first.page == second.page and first.y + first.h <= second.y + 0.1)


@pytest.mark.parametrize("kind", ["bar", "column"])
def test_build_draws_both_orientations_at_document_capacity(tmp_path, capsys, kind):
    data = {
        "type": kind,
        "category_label": "Period",
        "categories": [f"P{i + 1:02}" for i in range(24)],
        "series": [
            {"name": name, "values": [3 + (i * 7 + j * 11) % 43 for i in range(24)]}
            for j, name in enumerate(["Upland", "Lowland", "Riverside", "Hilltop", "Meadow"])
        ],
    }
    source = tmp_path / "capacity.md"
    source.write_text(FRONT + _section("trips", "chart", ["## Trips by zone", _data_block(data)]), encoding="utf-8")
    facts, sections, findings = _build(source, capsys)
    bars = _marks(facts, "trips", "chart-mark")
    expected = {
        f"data.series[{j}].values[{i}]": value
        for j, series in enumerate(data["series"])
        for i, value in enumerate(series["values"])
    }
    assert Counter(mark.field for mark in bars) == Counter(dict.fromkeys(expected, 1)), (
        f"A document {kind} chart must draw all 120 values at capacity"
    )
    spec = resolve_chart(data)
    assert sections[0]["content"]["chart"] == spec.model_dump(mode="json")
    manifest = all_manifests()[sections[0]["component"]]
    assert manifest.format == "doc" and manifest.name not in {"chart", "chart-table"}
    assert manifest.capacity["categories"][1] >= 24 and manifest.capacity["series"][1] >= 5
    labels = _marks(facts, "trips", "chart-label")
    assert Counter(label.field for label in labels) == Counter({f"data.categories[{i}]": 1 for i in range(24)})
    for i, category in enumerate(data["categories"]):
        label = next(label for label in labels if label.field == f"data.categories[{i}]")
        assert category in _text(facts, label)
    legends = _marks(facts, "trips", "chart-legend")
    assert legends
    legend_text = "".join(_text(facts, legend) for legend in legends)
    assert all(series["name"] in legend_text for series in data["series"])
    shapes = [shape for shape in facts.shapes if shape.section_id == "trips" and shape.role == "chart-mark"]
    assert len(shapes) == len(bars), "Chart marks must describe actual PDF shapes"
    assert Counter(shape.fill.upper() for shape in shapes) == Counter(
        {colour.upper(): 24 for colour in neutral_theme().colour.chart["categorical"][:5]}
    )
    dimension = "w" if kind == "bar" else "h"
    ratios = [getattr(mark, dimension) / expected[mark.field] for mark in bars]
    assert min(ratios) > 0
    assert ratios == pytest.approx([ratios[0]] * len(ratios), abs=0.02)
    # A document may flow vertically; no part of the chart may use the slide width.
    margin = 20 * 72 / 25.4
    for mark in [*bars, *labels, *legends]:
        page = next(page for page in facts.pages if page.page == mark.page)
        assert page.width == pytest.approx(595.276, abs=0.1)
        assert page.height == pytest.approx(841.89, abs=0.1)
        assert margin - 0.1 <= mark.x < mark.x + mark.w <= page.width - margin + 0.1
        assert 0 <= mark.y < mark.y + mark.h <= page.height + 0.1
    assert not [finding for finding in findings if finding["rule_id"] in {"source.capacity", "data.values-visible"}]


@pytest.mark.parametrize("kind", ["bar", "column"])
@pytest.mark.parametrize("data_slot", [0, 1, 2], ids=["data-first", "data-between", "data-last"])
def test_build_keeps_chart_prose_and_source_order_beside_unsupported_fallback(tmp_path, capsys, kind, data_slot):
    data = {
        "type": kind,
        "categories": ["Upland", "Lowland"],
        "series": [{"name": "Trips", "values": [17, 29]}, {"name": "Visits", "values": [23, 11]}],
    }
    blocks = list(PROSE)
    blocks.insert(data_slot, _data_block(data))
    drawn = _section("drawn", "chart", ["## Survey", *blocks, f"> source: {SOURCE}"])
    fallback = _section("fallback", "chart", ["## Unsupported shares", _data_block(data | {"type": "pie"})])
    source = tmp_path / "ordered.md"
    source.write_text(FRONT + (fallback + drawn if data_slot == 0 else drawn + fallback), encoding="utf-8")
    facts, sections, findings = _build(source, capsys)
    fallback_section = next(section for section in sections if section["id"] == "fallback")
    assert fallback_section["component"] == "chart-table"
    assert fallback_section["content"]["chart"] == resolve_chart(data | {"type": "pie"}).model_dump(mode="json")
    assert not _marks(facts, "fallback", "chart-mark")
    assert len(_marks(facts, "fallback", "table-cell")) == 6
    plots = _marks(facts, "drawn", "chart-plot")
    assert len(plots) == 1, "The drawable section must use the new document chart component"
    assert len(_marks(facts, "drawn", "chart-mark")) == 4
    paragraphs = []
    for i, text in enumerate(PROSE):
        marks = [
            mark
            for mark in facts.marks
            if isinstance(mark, ElementMark) and mark.id == "drawn" and mark.field == f"paragraphs[{i}]"
        ]
        assert len(marks) == 1
        assert text.replace(" ", "") in _text(facts, marks[0])
        paragraphs.append(marks[0])
    ordered = list(paragraphs)
    ordered.insert(data_slot, plots[0])
    for first, second in zip(ordered, ordered[1:], strict=False):
        _before(first, second)
    sources = _marks(facts, "drawn", "figure-source")
    assert len(sources) == 1 and sources[0].field == "source_line"
    assert SOURCE.replace(" ", "") in _text(facts, sources[0])
    for mark in ordered:
        _before(mark, sources[0])
    assert not [finding for finding in findings if finding["rule_id"] in {"geo.text-present", "data.values-visible"}]


@pytest.mark.parametrize("unknown_first", [False, True], ids=["chart-first", "unknown-first"])
def test_outline_deferral_is_per_section_and_does_not_hide_full_check_errors(tmp_path, capsys, unknown_first):
    intro = _section("intro", "body", ["## Scope", "Compare the survey zones."], section="introduction")
    pending = _section("pending", "chart", ["## Monthly trips"])
    unknown = _section("unknown", "invented-intent", ["## Unknown block"])
    ending = _section("end", "callout", ["## Next steps", "Review the survey limits."], section="findings")
    source = tmp_path / "outline.md"
    middle = unknown + pending if unknown_first else pending + unknown
    source.write_text(FRONT + intro + middle + ending, encoding="utf-8")
    out = tmp_path / "checks"
    code, output = _run(capsys, "check", source, "--outline", "--out", out)
    assert code == 1, output
    findings = json.loads((out / "outline.findings.json").read_bytes())
    hits = [finding for finding in findings if finding["rule_id"] == "source.intent-known"]
    assert Counter(finding["section_id"] for finding in hits) == Counter({"unknown": 1}), (
        "Outline deferral must suppress only the chart's missing-data error",
        hits,
    )
    source.write_text(FRONT + intro + pending + ending, encoding="utf-8")
    code, output = _run(capsys, "check", source, "--outline", "--out", out)
    assert code == 0 and "source.intent-known" not in output, output
    findings = json.loads((out / "outline.findings.json").read_bytes())
    assert not [finding for finding in findings if finding["rule_id"] == "source.intent-known"]
    code, output = _run(capsys, "check", source, "--out", out)
    assert code == 1 and "source.intent-known" in output, output
    findings = json.loads((out / "outline.findings.json").read_bytes())
    assert [finding["section_id"] for finding in findings if finding["rule_id"] == "source.intent-known"] == ["pending"]
    code, output = _run(capsys, "build", source)
    assert code != 0 and "source.intent-known" in output, output
