# Intent: every declared table and chart value is visible in its rendered field.
import importlib
import importlib.util
import runpy
from pathlib import Path

import pytest
import yaml

from ai_docs_kit import cli, source
from ai_docs_kit.checks import catalogue, engine
from ai_docs_kit.facts.layout import LayoutFacts, PlacedWord, layout_facts
from ai_docs_kit.facts.models import FactBox, PageFacts
from ai_docs_kit.model import Document, Section
from ai_docs_kit.render import compose, typst
from ai_docs_kit.render.marks import ElementMark
from ai_docs_kit.theme import neutral_theme

try:
    data = importlib.import_module("ai_docs_kit.checks.data")
except ImportError as error:
    if error.name != "ai_docs_kit.checks.data" or importlib.util.find_spec("ai_docs_kit.checks.data") is not None:
        raise
    data = None

ROOT = Path(__file__).resolve().parents[2]
SEEDED = ROOT / "tests/fixtures/seeded-defects/data.values-visible"


def _rule():
    rules = [rule for rule in catalogue.all_rules() if rule.id == "data.values-visible"]
    assert len(rules) == 1, "data.values-visible must be registered exactly once"
    return rules[0]


def _doc(section, fmt="slides"):
    front = {"doctype": "pitch-deck" if fmt == "slides" else "report", "title": "Data"}
    return Document(front=front, format=fmt, sections=[section])


def _run_check(doc, facts):
    return engine.run_checks([_rule()], engine.CheckContext(doc, facts, theme=neutral_theme()))


def _cli(path, out, capsys):
    try:
        code = cli.main(["check", str(path), "--out", str(out)])
    except SystemExit as error:
        code = error.code
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_D1_declared_values():
    assert data is not None and hasattr(data, "declared_values"), "declared_values must exist"
    assert data.declared_values({"columns": ["Quarter", "Revenue"], "rows": [["First", 120], ["Second", None]]}) == [
        ("data.columns[0]", "Quarter"),
        ("data.columns[1]", "Revenue"),
        ("data.rows[0][0]", "First"),
        ("data.rows[0][1]", "120"),
        ("data.rows[1][0]", "Second"),
    ]
    assert data.declared_values(
        {
            "type": "bar",
            "categories": ["North", 2024],
            "series": [
                {"name": "A", "values": [4, 6]},
                {"name": "B", "values": [3]},
            ],
        }
    ) == [
        ("data.categories[0]", "North"),
        ("data.categories[1]", "2024"),
        ("data.series[0].values[0]", None),
        ("data.series[0].values[1]", None),
        ("data.series[1].values[0]", None),
    ]
    assert data.declared_values({"x": "Cost", "y": "Value"}) == []
    assert data.declared_values(None) == []
    assert data.declared_values({"columns": [None, True, [], {}, "OK"], "rows": [[False, 2]]}) == [
        ("data.columns[4]", "OK"),
        ("data.rows[0][1]", "2"),
    ]


def test_D2_geometry_and_formats():
    rule = _rule()
    assert (rule.tier, rule.severity, rule.remedy.class_) == ("geometry", "error", "restructure")
    assert rule.check == {"kind": "values-visible"}
    section = Section(id="s1", intent="chart", data={"categories": ["North", "South"], "series": [{"values": [4, 6]}]})

    def mark(role, field, y):
        return ElementMark(kind="element", id="s1", role=role, field=field, page=1, x=10, y=y, w=100, h=20)

    marks = [
        mark("chart-label", "data.categories[0]", 10),
        mark("chart-label", "data.categories[1]", 40),
        mark("chart-mark", "data.series[0].values[0]", 70),
        mark("chart-mark", "data.series[0].values[1]", 100),
    ]
    assert getattr(marks[0], "field", None) == "data.categories[0]", "ElementMark.field must exist"

    def word(text, x, y):
        return PlacedWord(
            text=text,
            font="Test",
            size=10,
            colour="#000000",
            baseline=y + 8,
            box=FactBox(page=1, x0=x, y0=y, x1=x + 4, y1=y + 8),
            role="chart-label",
            section_id="s1",
        )

    words = [word("North", 12, 12), word("South", 12, 42)]

    def facts(ms, ws):
        return LayoutFacts(
            pdf_sha256="",
            pages=[PageFacts(page=1, width=960, height=540, words=[], shapes=[])],
            marks=ms,
            words=ws,
            shapes=[],
        )

    for fmt in ("slides", "doc"):
        doc = _doc(section, fmt)
        assert _run_check(doc, facts(marks, words)) == []
        missing = _run_check(doc, facts(marks[:-1], words))
        assert len(missing) == 1
        assert (missing[0].section_id, missing[0].role, missing[0].measured) == (
            "s1",
            "data",
            {"field": "data.series[0].values[1]", "value": None},
        )
        moved = _run_check(doc, facts(marks, [words[0], word("South", 200, 42)]))
        assert len(moved) == 1 and moved[0].measured["field"] == "data.categories[1]"
        letters = [word(letter, 12 + 5 * i, 42) for i, letter in enumerate("South")]
        assert _run_check(doc, facts(marks, [words[0], *letters])) == []
        off_page = [*marks[:3], marks[3].model_copy(update={"y": 600})]
        hits = _run_check(doc, facts(off_page, words))
        assert len(hits) == 1 and hits[0].measured["field"] == "data.series[0].values[1]"
        assert _run_check(doc, facts([], words)) == []
        assert _run_check(doc, None) == []


def test_D3_seeded_pair(tmp_path, capsys):
    _rule()
    fail_doc = SEEDED / "fail/doc.md"
    fixture = SEEDED / "fail/main.typ"
    assert fail_doc.is_file() and fixture.is_file(), "seeded fail files must exist"
    doc, parse_findings = source.parse(fail_doc.read_text())
    assert parse_findings == []
    root = tmp_path / "render"
    main = compose.assemble(compose.compose(doc), root, theme=neutral_theme())
    main.write_text(fixture.read_text())
    fonts = compose.font_paths(root)
    pdf = tmp_path / "fail.pdf"
    typst.compile_pdf(main, root, pdf, font_paths=fonts)
    findings = _run_check(doc, layout_facts(pdf, main, root, font_paths=fonts))
    assert [(f.section_id, f.measured["field"]) for f in findings] == [
        ("t1", "data.rows[2][0]"),
        ("t1", "data.rows[2][1]"),
        ("t1", "data.rows[2][2]"),
    ]
    passing = SEEDED / "pass/doc.md"
    assert passing.is_file(), "seeded pass doc.md must exist"
    code, out, err = _cli(passing, tmp_path / "pass", capsys)
    assert code == 0, out + err
    assert "data.values-visible" not in out


@pytest.mark.parametrize("name", ["chart", "table", "SLIDES", "DOC"])
def test_D4_clean_decks(name, tmp_path, capsys):
    if name in ("chart", "table"):
        section = Section.model_validate(yaml.safe_load((ROOT / f"tests/fixtures/components/{name}.yaml").read_text()))
        text = source.serialise(_doc(section))
    else:
        text = runpy.run_path(str(ROOT / "tests/judge/test_m1_17_cli_build_check.py"))[name]
    path = tmp_path / "deck.md"
    path.write_text(text)
    code, out, err = _cli(path, tmp_path / "out", capsys)
    assert code == 0, out + err
    assert out.splitlines() == ["no findings"]
