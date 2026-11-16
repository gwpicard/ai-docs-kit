# Intent: resolved chart specifications are stored and drive chart rendering and checks.
import importlib
import importlib.util
import json
import re
from pathlib import Path

import yaml

from ai_docs_kit.checks import charts, engine
from ai_docs_kit.facts.layout import LayoutFacts, layout_facts
from ai_docs_kit.facts.models import PageFacts
from ai_docs_kit.model import Document, Item, Section
from ai_docs_kit.render import compose, swatch
from ai_docs_kit.render.marks import ElementMark
from ai_docs_kit.render.typst import compile_pdf
from ai_docs_kit.testing.golden import compare_facts, facts_for
from ai_docs_kit.theme import neutral_theme

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/components"

try:
    chart_spec = importlib.import_module("ai_docs_kit.render.chart_spec")
except ImportError as error:
    if error.name != "ai_docs_kit.render.chart_spec" or importlib.util.find_spec("ai_docs_kit.render.chart_spec") is not None:
        raise
    chart_spec = None


def _resolve(data):
    assert chart_spec is not None and hasattr(chart_spec, "resolve_chart"), "resolve_chart must exist"
    return chart_spec.resolve_chart(data).model_dump(mode="json")


def _fixture():
    return Section.model_validate(yaml.safe_load((FIXTURES / "chart.yaml").read_text()))


def _doc(*sections):
    return Document(front={"doctype": "pitch-deck", "title": "Charts"}, format="slides", sections=list(sections))


def _render(comp, dest):
    main = compose.assemble(comp, dest, theme=neutral_theme())
    pdf = dest / "out.pdf"
    compile_pdf(main, dest, pdf, font_paths=compose.font_paths(dest))
    return layout_facts(pdf, main, dest)


def _marks(facts):
    return [m for m in facts.marks if isinstance(m, ElementMark) and m.role == "chart-mark"]


def test_D1_composition_and_resolved_column(tmp_path):
    section = _fixture()
    bullets = Section(id="b1", intent="bullets", title="Points", items=[Item(body="One")])
    comp = compose.compose(_doc(section, bullets))
    assert comp.sections[0].content.get("chart") == _resolve(section.data)
    assert comp.sections[0].content["data"] == section.data
    assert set(comp.sections[1].content) == {"data", "image", "citations", "icons"}
    data = {"categories": ["2022", "2023", "2024"], "series": [{"name": "Sales", "values": [1, 2, 4]}]}
    timed = Section(id="s1", intent="chart", title="Sales", data=data)
    doc = _doc(timed)
    assert compose.compose(doc).sections[0].content.get("chart", {}).get("type") == "column"
    facts = swatch.swatch(doc, "s1", tmp_path, theme=neutral_theme()).facts
    heights = sorted(m.h for m in _marks(facts))
    assert len(heights) == 3 and heights[0] > 0
    assert abs(heights[1] - 2 * heights[0]) <= 0.5
    assert abs(heights[2] - 4 * heights[0]) <= 0.5


def test_D2_golden_and_chart_source():
    golden = json.loads((FIXTURES / "chart.facts.json").read_text())
    assert compare_facts(facts_for("chart", FIXTURES), golden) == []
    source = (ROOT / "src/ai_docs_kit/render/library/chart.typ").read_text()
    assert "sec.data" not in source
    assert 'at("data"' not in source
    assert "chart-colour" not in source
    assert not re.search(r"\b(?:rgb|luma|cmyk)\s*\(|#[0-9a-fA-F]{6}\b", source)


def test_D3_render_uses_spec_not_raw_data(tmp_path):
    comp = compose.compose(_doc(_fixture()))
    assert "chart" in comp.sections[0].content, "chart specification must be stored"
    changed = comp.model_copy(deep=True)
    changed.sections[0].content["chart"]["categories"][0] = "Zeta"
    facts = _render(changed, tmp_path / "spec")
    labels = [w.text for w in facts.words if w.role == "chart-label"]
    assert "Zeta" in labels and "North" not in labels
    changed = comp.model_copy(deep=True)
    changed.sections[0].content["data"]["categories"][0] = "Ignored"
    facts = _render(changed, tmp_path / "data")
    labels = [w.text for w in facts.words if w.role == "chart-label"]
    assert "North" in labels and "Ignored" not in labels
    changed = comp.model_copy(deep=True)
    changed.sections[0].content["chart"]["type"] = "unsupported"
    facts = _render(changed, tmp_path / "unsupported")
    assert "chart type not supported" in " ".join(w.text for w in facts.words).lower()
    assert _marks(facts) == []


def test_D4_series_colours_follow_spec_references(tmp_path):
    comp = compose.compose(_doc(_fixture()))
    assert "chart" in comp.sections[0].content, "chart specification must be stored"
    palettes = neutral_theme().colour.chart

    def fills(facts):
        return [s.fill.upper() for s in facts.shapes if s.role == "chart-mark"]

    colours = fills(_render(comp, tmp_path / "original"))
    assert colours == [palettes["categorical"][0], palettes["categorical"][1]] * 4
    for palette, index, folder in [("categorical", 2, "third"), ("sequence", 0, "sequence")]:
        changed = comp.model_copy(deep=True)
        changed.sections[0].content["chart"]["series"][0]["colour"] = {"palette": palette, "index": index}
        colours = fills(_render(changed, tmp_path / folder))
        assert colours == [palettes[palette][index], palettes["categorical"][1]] * 4


def test_D5_resolved_type_checks_mark_lengths():
    data = {"categories": ["A", "B"], "series": [{"name": "Sales", "values": [1, 2]}]}
    section = Section(id="s1", intent="chart", title="Sales", data=data)
    doc = _doc(section)
    comp = compose.compose(doc)
    spec = _resolve(data)
    assert spec["type"] == "bar"
    comp.sections[0].content["chart"] = spec
    rule = next(r for r in charts.RULES if r.id == "geo.chart-labels")

    def check(first_width):
        marks = [
            ElementMark(kind="element", id="s1", role="chart-mark", page=1, x=100, y=100 + i * 20, w=w, h=12)
            for i, w in enumerate([first_width, 100])
        ]
        facts = LayoutFacts(
            pdf_sha256="0" * 64,
            pages=[PageFacts(page=1, width=960, height=540, words=[], shapes=[])],
            words=[],
            shapes=[],
            marks=marks,
        )
        ctx = engine.CheckContext(doc=doc, facts=facts, composition=comp, theme=neutral_theme())
        return engine.run_checks([rule], ctx)

    assert any(f.role == "chart-mark" for f in check(100))
    assert check(50) == []
