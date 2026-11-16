from ai_docs_kit.model import Document, Section
from ai_docs_kit.render import swatch
from ai_docs_kit.render.marks import ElementMark
from ai_docs_kit.theme import neutral_theme


def _marks(chart_type, tmp_path):
    data = {"categories": ["a", "b"], "series": [{"name": "s", "values": [-5, 3]}], "type": chart_type}
    section = Section(id="s1", intent="chart", title="Mixed", data=data)
    doc = Document(front={"doctype": "pitch-deck", "title": "Charts"}, format="slides", sections=[section])
    facts = swatch.swatch(doc, "s1", tmp_path, theme=neutral_theme()).facts
    return [m for m in facts.marks if isinstance(m, ElementMark) and m.role == "chart-mark"]


def test_column_negative_value_is_drawn_below_baseline(tmp_path):
    negative, positive = _marks("column", tmp_path)
    assert abs(negative.h - 5 * positive.h / 3) <= 0.5
    assert negative.y >= positive.y + positive.h - 0.5


def test_bar_negative_value_is_drawn_left_of_baseline(tmp_path):
    negative, positive = _marks("bar", tmp_path)
    assert abs(negative.w - 5 * positive.w / 3) <= 0.5
    assert negative.x + negative.w <= positive.x + 0.5
