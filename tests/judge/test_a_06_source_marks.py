# Intent: Rendered numbers link their word boxes to fields and supporting facts.
import importlib.util
import json
from pathlib import Path

import yaml

try:
    import ai_docs_kit.facts.numbers as numbers
except ImportError as error:
    if error.name != "ai_docs_kit.facts.numbers" and not (
        error.name and error.name.startswith("ai_docs_kit.facts.numbers.")
        and importlib.util.find_spec(error.name) is None
    ):
        raise
    numbers = None

from ai_docs_kit.agents import gatherer
from ai_docs_kit.facts.layout import layout_facts
from ai_docs_kit.model import Document, Section
from ai_docs_kit.render import compose, typst
from ai_docs_kit.testing.golden import compare_facts, facts_for
from ai_docs_kit.theme import neutral_theme

FIXTURES = Path(__file__).resolve().parents[2] / "tests/fixtures/components"


def api(*names):
    assert numbers is not None, "ai_docs_kit.facts.numbers must exist"
    for name in names:
        assert hasattr(numbers, name), f"ai_docs_kit.facts.numbers.{name} must exist"
    return numbers


def workbook_facts(tmp_path):
    assert importlib.util.find_spec("openpyxl") is not None, "openpyxl must be installed"
    from openpyxl import Workbook
    from ai_docs_kit.tables import table_facts

    assert hasattr(gatherer, "with_fact_ids"), "with_fact_ids must exist"
    book = Workbook()
    sheet = book.active
    sheet.title = "Sales"
    sheet.append(["Region", "Revenue", "Margin", "Closed", "Deals"])
    sheet.append(["North", 1234500, 0.125, None, 42])
    sheet["B2"].number_format = '"£"#,##0'
    sheet["C2"].number_format = "0.0%"
    path = tmp_path / "sales.xlsx"
    book.save(path)
    return gatherer.with_fact_ids(table_facts(path, "S1", typed=True))


def render(tmp_path, section, fmt="slides"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    composition = compose.compose(Document(front={}, format=fmt, sections=[section]))
    root = tmp_path / "render"
    main = compose.assemble(composition, root, theme=neutral_theme())
    pdf = tmp_path / "out.pdf"
    fonts = compose.font_paths(root)
    typst.compile_pdf(main, root, pdf, fonts)
    return layout_facts(pdf, main, root, font_paths=fonts), composition


def slide(locator="Sales!B2"):
    return Section(id="s1", intent="bullets", title="North", items=[
        {"body": "Revenue reached £1,234,500 at a 12.5% margin", "citations": [{"key": "S1", "locator": locator}]},
        {"body": "Deals closed: 42", "citations": [{"key": "S1", "locator": "Sales!E2"}]},
    ])


def rows(marks):
    return [(m.section, m.field, m.text, m.token, m.cited, m.facts) for m in marks]


def ids(facts):
    return {f.locator: f.id for f in facts}


def test_D1_cited_numbers_and_word_boxes(tmp_path):
    module = api("SourceMark", "source_marks")
    facts = workbook_facts(tmp_path)
    layout, composition = render(tmp_path, slide())
    result = module.source_marks(layout, composition, facts)
    by_cell = ids(facts)
    assert rows(result) == [
        ("s1", "items[0]", "1,234,500", "1234500", True, [by_cell["Sales!B2"]]),
        ("s1", "items[0]", "12.5%", "12.5%", True, []),
        ("s1", "items[1]", "42", "42", True, [by_cell["Sales!E2"]]),
    ]
    assert all(isinstance(mark, module.SourceMark) for mark in result)
    for mark in result:
        assert mark.page == 1 and mark.w > 0 and mark.h > 0
        assert any(mark.text in word.text and word.box.page == mark.page
                   and mark.x <= (word.box.x0 + word.box.x1) / 2 <= mark.x + mark.w
                   and mark.y <= (word.box.y0 + word.box.y1) / 2 <= mark.y + mark.h
                   for word in layout.words)


def test_D2_citation_scope_and_printed_locator(tmp_path):
    module = api("source_marks")
    facts = workbook_facts(tmp_path)
    layout, composition = render(tmp_path / "broad", slide(None))
    result = module.source_marks(layout, composition, facts)
    assert len(result) == 3
    assert result[1].facts == [ids(facts)["Sales!C2"]]
    section = Section(id="s1", intent="bullets", title="North", items=[
        {"body": "Short intervals catch drift early in 41 sites.", "citations": [{"key": "S1", "locator": "00:41"}]},
        {"body": "Q3"},
    ])
    layout, composition = render(tmp_path / "locator", section)
    result = module.source_marks(layout, composition, facts)
    assert [(m.field, m.text, m.token, m.cited, m.facts) for m in result] == [("items[0]", "41", "41", True, [])]


def test_D3_unresolved_marks_and_field_text(tmp_path):
    module = api("number_marks", "field_text")
    layout, composition = render(tmp_path, slide())
    assert rows(module.number_marks(layout, composition)) == [
        ("s1", "items[0]", "1,234,500", "1234500", True, []),
        ("s1", "items[0]", "12.5%", "12.5%", True, []),
        ("s1", "items[1]", "42", "42", True, []),
    ]
    section = composition.sections[0]
    assert module.field_text(section, "items[0].body") == "Revenue reached £1,234,500 at a 12.5% margin"
    joined = compose.compose(Document(front={}, format="slides", sections=[
        Section(id="s2", intent="bullets", items=[{"head": "Q1", "body": "Revenue grew"}])
    ])).sections[0]
    assert module.field_text(joined, "items[0]") == "Q1 Revenue grew"
    table = Section.model_validate(yaml.safe_load((FIXTURES / "table.yaml").read_text()))
    table_section = compose.compose(Document(front={}, format="slides", sections=[table])).sections[0]
    assert module.field_text(table_section, "data.rows[0][1]") == "120"
    assert [module.field_text(section, path) for path in ("items[9]", "note", "data.missing")] == [None, None, None]


def test_D4_document_paragraph_and_table_cells(tmp_path):
    module = api("source_marks")
    facts = workbook_facts(tmp_path)
    section = Section(id="d1", intent="body", title="Findings", paragraphs=["Revenue reached £1,234,500 in the North."])
    layout, composition = render(tmp_path / "doc", section, "doc")
    assert rows(module.source_marks(layout, composition, facts)) == [
        ("d1", "paragraphs[0]", "1,234,500", "1234500", False, [ids(facts)["Sales!B2"]])
    ]
    table = Section.model_validate(yaml.safe_load((FIXTURES / "table.yaml").read_text()))
    layout, composition = render(tmp_path / "table", table)
    result = module.source_marks(layout, composition, facts)
    assert [(m.field, m.text, m.facts) for m in result] == [
        ("data.rows[0][1]", "120", []), ("data.rows[0][2]", "5%", []),
        ("data.rows[1][1]", "130", []), ("data.rows[1][2]", "8%", []),
        ("data.rows[2][1]", "140", []), ("data.rows[2][2]", "7%", []),
        ("data.rows[3][1]", "150", []), ("data.rows[3][2]", "6%", []),
    ]


def test_D5_component_golden_facts_stay_equal():
    files = sorted(FIXTURES.glob("*.facts.json"))
    assert files
    for path in files:
        name = path.name.removesuffix(".facts.json")
        assert compare_facts(facts_for(name, FIXTURES), json.loads(path.read_text())) == [], name
