# Intent: a multi-series chart labels each category once, centred on its group, and its legend shows each series' colour.
from pathlib import Path

import pytest
import yaml

from ai_docs_kit.checks import charts, engine
from ai_docs_kit.facts.layout import LayoutFacts
from ai_docs_kit.facts.models import PageFacts
from ai_docs_kit.model import Document, Section
from ai_docs_kit.render import compose, swatch
from ai_docs_kit.render.marks import ElementMark
from ai_docs_kit.theme import neutral_theme

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/components/chart.yaml"
CATEGORIES = ["North", "South", "East", "West"]
SERIES = ["Current", "Previous"]


def _section(chart_type="bar", series=2):
    data = yaml.safe_load(FIXTURE.read_text())["data"]
    data = {**data, "type": chart_type, "series": data["series"][:series]}
    return Section(id="chart1", intent="chart", title="Quarterly results", data=data)


def _doc(section):
    return Document(front={"doctype": "pitch-deck", "title": "Chart"}, format="slides", sections=[section])


def _render(section, tmp_path):
    return swatch.swatch(_doc(section), section.id, tmp_path, theme=neutral_theme()).facts


def _role(facts, role):
    return [m for m in facts.marks if isinstance(m, ElementMark) and m.role == role]


def _groups(marks, count):
    per = len(marks) // count
    return [marks[i * per:(i + 1) * per] for i in range(count)]


def test_bar_labels_once_per_category_centred_on_group(tmp_path):
    facts = _render(_section("bar"), tmp_path)
    labels = _role(facts, "chart-label")
    assert [m.field for m in labels] == [f"data.categories[{i}]" for i in range(4)]
    words = [w.text for p in facts.pages for w in p.words if w.text in CATEGORIES]
    assert words == CATEGORIES
    for label, group in zip(labels, _groups(_role(facts, "chart-mark"), 4), strict=True):
        centre = (min(m.y for m in group) + max(m.y + m.h for m in group)) / 2
        assert abs(label.y + label.h / 2 - centre) <= 4


def test_column_labels_once_per_category_centred_on_group(tmp_path):
    facts = _render(_section("column"), tmp_path)
    labels = _role(facts, "chart-label")
    assert [m.field for m in labels] == [f"data.categories[{i}]" for i in range(4)]
    for label, group in zip(labels, _groups(_role(facts, "chart-mark"), 4), strict=True):
        centre = (min(m.x for m in group) + max(m.x + m.w for m in group)) / 2
        assert abs(label.x + label.w / 2 - centre) <= 4


@pytest.mark.parametrize("chart_type", ["bar", "column"])
def test_legend_has_swatch_in_each_series_colour(tmp_path, chart_type):
    facts = _render(_section(chart_type), tmp_path)
    page = facts.pages[0]
    marks = _role(facts, "chart-mark")
    fills = []
    for j in range(2):
        mark = next(m for m in marks if m.field == f"data.series[{j}].values[0]")
        cx, cy = mark.x + mark.w / 2, mark.y + mark.h / 2
        shape = next(s for s in page.shapes if s.fill and s.box.x0 <= cx <= s.box.x1 and s.box.y0 <= cy <= s.box.y1)
        fills.append(shape.fill)
    assert fills[0] != fills[1]
    for name, fill in zip(SERIES, fills, strict=True):
        word = next(w for w in page.words if w.text == name)
        before = [
            s for s in page.shapes
            if s.fill == fill and s.box.y0 < word.box.y1 and s.box.y1 > word.box.y0
            and word.box.x0 - 24 <= s.box.x1 <= word.box.x0 + 1
        ]
        assert before, f"no swatch in {fill} just before legend entry {name}"


@pytest.mark.parametrize("chart_type", ["bar", "column"])
def test_single_series_keeps_one_label_per_bar_and_no_legend(tmp_path, chart_type):
    facts = _render(_section(chart_type, series=1), tmp_path)
    assert len(_role(facts, "chart-label")) == 4
    assert len(_role(facts, "chart-mark")) == 4
    assert _role(facts, "chart-legend") == []


def _check(labels, composition):
    marks = [
        ElementMark(kind="element", id="chart1", role="chart-mark", page=1, x=160, y=y, w=100, h=12, field=f"data.series[{j}].values[{i}]")
        for i, y0 in enumerate((100, 200))
        for j, y in enumerate((y0, y0 + 12))
    ]
    marks += [
        ElementMark(kind="element", id="chart1", role="chart-label", page=1, x=40, y=y, w=48, h=12, field=f"data.categories[{i}]")
        for i, y in enumerate(labels)
    ]
    facts = LayoutFacts(
        pdf_sha256="0" * 64,
        pages=[PageFacts(page=1, width=960, height=540, words=[], shapes=[])],
        words=[],
        shapes=[],
        marks=marks,
    )
    section = Section(id="chart1", intent="chart", data={
        "type": "bar",
        "categories": ["A", "B"],
        "series": [{"name": "S0", "values": [4, 4]}, {"name": "S1", "values": [4, 4]}],
    })
    doc = _doc(section)
    ctx = engine.CheckContext(doc=doc, facts=facts, theme=neutral_theme(), composition=composition(doc))
    rule = next(r for r in charts.RULES if r.id == "geo.chart-labels")
    return [f for f in engine.run_checks([rule], ctx) if f.rule_id == "geo.chart-labels"]


def test_check_pairs_label_with_its_own_group_when_data_known():
    assert _check([106, 206], compose.compose) == []


def test_check_flags_label_away_from_its_own_group_when_data_known():
    hits = _check([106, 106], compose.compose)
    assert [h.measured["label"] for h in hits] == [1]
