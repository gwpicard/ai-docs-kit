"""Judge issue 388 through chart resolution, real builds and the golden oracle."""

import json
import shutil
import subprocess
import sys
from collections import Counter
from math import dist
from pathlib import Path

import pdfplumber
import pytest
import yaml

from ai_docs_kit.cli import main
from ai_docs_kit.facts.layout import LayoutFacts
from ai_docs_kit.facts.pdf import to_hex
from ai_docs_kit.render.chart_spec import ChartSpec, resolve_chart
from ai_docs_kit.render.marks import ElementMark
from ai_docs_kit.testing.golden import compare_facts
from ai_docs_kit.theme import NEUTRAL_ROOT, neutral_theme

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/components"


def _monthly(reverse=False):
    data = {
        "type": "line",
        "ordered": True,
        "unit": "kg",
        "category_label": "Month",
        "categories": "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(),
        "series": [
            {"name": "Upland", "values": [-4, 2, 8, 4, 10, 6, 12, 8, 14, 10, 16, 0]},
            {"name": "Lowland", "values": [3, 9, 5, 11, 7, 13, 9, 15, 11, 17, 13, 7]},
            {
                "name": "Riverside",
                "values": [1.25, 7.25, 3.25, 9.25, 5.25, 11.25, 7.25, 13.25, 9.25, 15.25, 11.25, 5.25],
            },
        ],
    }
    if reverse:
        data["categories"].reverse()
        data["series"].reverse()
        for series in data["series"]:
            series["values"].reverse()
    return data


@pytest.mark.parametrize("reverse", [False, True], ids=["forward", "reversed-categories-and-series"])
def test_explicit_line_spec_preserves_column_data_scale_labels_and_twin_table(reverse):
    data = _monthly(reverse)
    column = resolve_chart(data | {"type": "column"})
    # The implicit chooser still selects column, even for ordered trend data.
    implicit = resolve_chart({key: value for key, value in data.items() if key != "type"})
    assert implicit.type == implicit.chosen == "column"
    spec = resolve_chart(data)
    assert spec.type == "line", "An explicit line request must resolve to a drawable line specification"
    assert spec.requested == "line" and spec.chosen == "column"
    assert spec.model_dump(exclude={"type", "requested"}) == column.model_dump(exclude={"type", "requested"})
    assert spec.categories == data["categories"]
    assert (spec.scale.min, spec.scale.max, spec.scale.decimals) == (-4, 17, 2)
    assert spec.legend is True
    assert [series.values for series in spec.series] == [series["values"] for series in data["series"]]
    expected_labels = [[f"{value:,.2f} kg" for value in series["values"]] for series in data["series"]]
    assert [series.labels for series in spec.series] == expected_labels
    assert [(series.colour.palette, series.colour.index) for series in spec.series] == [
        ("categorical", j) for j in range(3)
    ]
    assert spec.table is not None
    assert spec.table.columns == ["Month", *(series["name"] for series in data["series"])]
    assert spec.table.rows == [
        [category, *(labels[i] for labels in expected_labels)] for i, category in enumerate(data["categories"])
    ]
    assert ChartSpec.model_validate_json(spec.model_dump_json()) == spec


def _build(folder, capsys, data, *, fmt="doc", theme=None):
    folder.mkdir(parents=True)
    source = folder / "trend.md"
    source.write_text(
        f'---\nformat: {fmt}\n---\n\n::: {{#trend .section intent="chart"}}\n'
        "## Survey trend\n\n```data\n" + yaml.safe_dump(data, sort_keys=False) + "```\n:::\n",
        encoding="utf-8",
    )
    args = ["build", str(source)]
    if theme is not None:
        args += ["--theme", str(theme)]
    code = main(args)
    captured = capsys.readouterr()
    assert code == 0, captured.out + captured.err
    version = folder / "trend.versions/v1"
    assert (version / "trend.pdf").is_file()
    facts = LayoutFacts.model_validate_json((version / "layout.json").read_bytes())
    composition = json.loads((version / "composition.json").read_bytes())
    findings = json.loads((version / "findings.json").read_bytes())
    return version, facts, composition["sections"][0], findings


def _marks(facts, role):
    return [mark for mark in facts.marks if isinstance(mark, ElementMark) and mark.id == "trend" and mark.role == role]


def _centre(mark):
    return mark.x + mark.w / 2, mark.y + mark.h / 2


def _text(facts, mark):
    return "".join(
        word.text
        for word in facts.words
        if word.box.page == mark.page
        and mark.x - 0.5 <= (word.box.x0 + word.box.x1) / 2 <= mark.x + mark.w + 0.5
        and mark.y - 0.5 <= (word.box.y0 + word.box.y1) / 2 <= mark.y + mark.h + 0.5
    ).replace(" ", "")


def _segments(page, colour):
    # PDF facts keep bounding boxes only. Read the PDF paths to prove the points are joined.
    result = []
    for shape in [*page.lines, *page.curves]:
        if shape.get("stroke") and to_hex(shape.get("stroking_color")) == colour.upper():
            points = shape["pts"]
            result.extend(zip(points, points[1:], strict=False))
    return result


def _assert_points_and_lines(version, facts, data, palette):
    marks = _marks(facts, "chart-mark")
    expected = {
        f"data.series[{j}].values[{i}]": value
        for j, series in enumerate(data["series"])
        for i, value in enumerate(series["values"])
    }
    assert Counter(mark.field for mark in marks) == Counter(dict.fromkeys(expected, 1)), (
        "A document line chart must mark each value once, using data.series[j].values[i]"
    )
    by_field = {mark.field: mark for mark in marks}
    plots = _marks(facts, "chart-plot")
    assert len(plots) == 1
    plot = plots[0]
    with pdfplumber.open(version / "trend.pdf") as pdf:
        slopes, intercepts = [], []
        for j, series in enumerate(data["series"]):
            points = [by_field[f"data.series[{j}].values[{i}]"] for i in range(len(data["categories"]))]
            centres = [_centre(point) for point in points]
            xs, ys = zip(*centres, strict=True)
            assert all(right > left for left, right in zip(xs, xs[1:], strict=False)), (
                "Categories must run left to right in their declared order"
            )
            gaps = [right - left for left, right in zip(xs, xs[1:], strict=False)]
            assert gaps == pytest.approx([gaps[0]] * len(gaps), abs=0.5)
            assert all(point.page == plot.page for point in points)
            if j:
                first_xs = [_centre(by_field[f"data.series[0].values[{i}]"])[0] for i in range(len(xs))]
                assert xs == pytest.approx(first_xs, abs=0.5), "Series share category positions, without bar offsets"
            values = series["values"]
            low, high = min(range(len(values)), key=values.__getitem__), max(range(len(values)), key=values.__getitem__)
            slope = (ys[high] - ys[low]) / (values[high] - values[low])
            assert slope < 0, "Larger values sit higher on the page"
            intercept = ys[low] - slope * values[low]
            slopes.append(slope)
            intercepts.append(intercept)
            assert ys == pytest.approx([intercept + slope * value for value in values], abs=0.5)
            for value, y in zip(values, ys, strict=True):
                if value < 0:
                    assert y > intercept, "Negative values must sit below zero"
                elif value == 0:
                    assert y == pytest.approx(intercept, abs=0.5)
            colour = palette[j].upper()
            segments = _segments(pdf.pages[plot.page - 1], colour)
            for start, end in zip(centres, centres[1:], strict=False):
                assert any(
                    (dist(a, start) <= 0.75 and dist(b, end) <= 0.75)
                    or (dist(b, start) <= 0.75 and dist(a, end) <= 0.75)
                    for a, b in segments
                ), f"Series {j} needs a {colour} line joining {start} to {end}"
            for point, (x, y) in zip(points, centres, strict=True):
                assert plot.x - 0.5 <= x <= plot.x + plot.w + 0.5
                assert plot.y - 0.5 <= y <= plot.y + plot.h + 0.5
                assert any(
                    shape.section_id == "trend"
                    and shape.box.page == point.page
                    and colour in (shape.fill, shape.stroke)
                    and dist(((shape.box.x0 + shape.box.x1) / 2, (shape.box.y0 + shape.box.y1) / 2), (x, y)) <= 0.75
                    for shape in facts.shapes
                ), f"Point {point.field} must describe a visible shape in its series colour"
        assert slopes == pytest.approx([slopes[0]] * len(slopes), abs=0.02)
        assert intercepts == pytest.approx([intercepts[0]] * len(intercepts), abs=0.5)


@pytest.mark.parametrize("case", ["monthly", "reversed", "signed-single"])
def test_build_draws_ordered_lines_points_labels_and_legend_without_changing_slides(tmp_path, capsys, case):
    data = _monthly(case == "reversed")
    if case == "signed-single":
        data["categories"] = ["Last", "First", "Middle", "End"]
        data["series"] = [{"name": "Upland", "values": [0, -6, 9, -3]}]
    slide_data = data | {
        "categories": data["categories"][:4],
        "series": [series | {"values": series["values"][:4]} for series in data["series"]],
    }
    _, slide, slide_section, _ = _build(tmp_path / "slides", capsys, slide_data, fmt="slides")
    assert slide_section["component"] == "chart"
    assert not any(_marks(slide, role) for role in ("chart-mark", "chart-plot", "chart-label", "chart-legend"))
    assert "charttypenotsupported" in "".join(word.text for word in slide.words).replace(" ", "")

    version, facts, section, findings = _build(tmp_path / "doc", capsys, data)
    _assert_points_and_lines(version, facts, data, neutral_theme().colour.chart["categorical"])
    assert section["component"] == "doc-chart", "Use the existing document chart component"
    assert section["content"]["chart"] == resolve_chart(data).model_dump(mode="json")
    labels = _marks(facts, "chart-label")
    assert Counter(mark.field for mark in labels) == Counter(
        {f"data.categories[{i}]": 1 for i in range(len(data["categories"]))}
    )
    for i, category in enumerate(data["categories"]):
        label = next(mark for mark in labels if mark.field == f"data.categories[{i}]")
        assert category in _text(facts, label)
    if len(data["series"]) >= 2:
        legends = _marks(facts, "chart-legend")
        assert legends
        assert all(series["name"] in "".join(_text(facts, mark) for mark in legends) for series in data["series"])
    assert not [finding for finding in findings if finding["rule_id"] in {"geo.palette", "data.values-visible"}]


def test_build_uses_the_selected_themes_categorical_colours_for_lines_and_points(tmp_path, capsys):
    theme = tmp_path / "theme"
    shutil.copytree(NEUTRAL_ROOT, theme)
    tokens_path = theme / "tokens.yaml"
    tokens = yaml.safe_load(tokens_path.read_text(encoding="utf-8"))
    palette = ["#B5462B", "#2A7F62", "#5B4B8A", "#C99A2E", "#14213D", "#7C8BA8"]
    tokens["colour"]["chart"]["categorical"] = palette
    tokens_path.write_text(yaml.safe_dump(tokens, sort_keys=False), encoding="utf-8")
    data = _monthly()
    version, facts, _, findings = _build(tmp_path / "doc", capsys, data, theme=theme)
    _assert_points_and_lines(version, facts, data, palette)
    assert not [finding for finding in findings if finding["rule_id"] in {"geo.palette", "data.values-visible"}]


def test_line_component_fixture_has_drawn_marks_and_matches_the_golden_script(tmp_path):
    candidates = []
    for path in sorted(FIXTURES.glob("*.yaml")):
        fixture = yaml.safe_load(path.read_text(encoding="utf-8"))
        if fixture.get("component", path.stem) == "doc-chart" and (fixture.get("data") or {}).get("type") == "line":
            candidates.append((path, fixture))
    assert candidates, "Ship a line fixture for doc-chart and generate its facts with scripts/golden_facts.py"
    for path, fixture in candidates:
        golden = path.with_suffix(".facts.json")
        assert golden.is_file(), f"Generate {golden.name} with scripts/golden_facts.py"
        expected = json.loads(golden.read_bytes())
        count = sum(len(series["values"]) for series in fixture["data"]["series"])
        assert count > 0
        assert len(expected.get("chart-mark", {}).get("marks", [])) == count
        assert expected.get("chart-label", {}).get("words")
        if len(fixture["data"]["series"]) >= 2:
            assert expected.get("chart-legend", {}).get("words")
        assert not expected.get("table-cell", {}).get("marks"), "A fallback table cannot be the line golden"
        shutil.copyfile(path, tmp_path / path.name)
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/golden_facts.py"), path.stem, "--fixtures", str(tmp_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        actual = json.loads((tmp_path / golden.name).read_bytes())
        assert compare_facts(actual, expected) == []
