# Intent: Measure PDF vector marks and derive separate grids for each format.
import importlib
import importlib.util

import pytest

from ai_docs_kit import cli
from ai_docs_kit.brand.git import run_git
from ai_docs_kit.brand.workspace import init_brand
from ai_docs_kit.render.typst import compile_pdf


def _module(name):
    try:
        return importlib.import_module(name)
    except ImportError as error:
        if error.name != name or importlib.util.find_spec(name) is not None:
            raise
        return None


vectors = _module("ai_docs_kit.brand.vectors")
pages = _module("ai_docs_kit.brand.pages")
intake = _module("ai_docs_kit.brand.intake")
changes = _module("ai_docs_kit.brand.changes")


def _require(module, *names):
    assert module is not None, "required public module must exist"
    for name in names:
        assert hasattr(module, name), f"{module.__name__}.{name} must exist"


def _pdf(brand, relative, source):
    output = brand / relative
    source_path = output.with_suffix(".typ")
    source_path.write_text(source)
    compile_pdf(source_path, brand, output)
    source_path.unlink()


def _fixture(tmp_path):
    _require(vectors, "measure_vectors", "unit_grid", "VectorReport")
    _require(pages, "parse_pdfs", "PageIndex")
    _require(intake, "take_in")
    brand = init_brand("acme", tmp_path / ".brand")
    deck = """#set page(width: 960pt, height: 540pt, margin: 0pt)
#let drawing() = {
  place(top + left, rect(width: 960pt, height: 540pt, fill: rgb("#F5F5F5"), stroke: none))
  place(top + left, dx: 48pt, dy: 45pt, line(length: 240pt, stroke: rgb("#0B5FFF")))
  place(top + left, dx: 96pt, dy: 90pt, line(length: 144pt, stroke: (paint: black, thickness: 0.5pt)))
  place(top + left, dx: 96pt, dy: 135pt, rect(width: 144pt, height: 90pt, fill: rgb("#E4002B"), stroke: none))
  place(top + left, dx: 480pt, dy: 135pt, rect(width: 240pt, height: 2pt, fill: rgb("#111111"), stroke: none))
  place(top + left, dx: 480pt, dy: 270pt, ellipse(width: 96pt, height: 90pt, fill: rgb("#00A651"), stroke: none))
  place(top + left, dx: 672pt, dy: 360pt,
    rect(width: 96pt, height: 45pt, stroke: (paint: rgb("#111111"), thickness: 3pt)))
}
#drawing()
#pagebreak()
#drawing()
"""
    doc = """#set page(width: 600pt, height: 840pt, margin: 0pt)
#place(top + left, dx: 50pt, dy: 42pt, rect(width: 100pt, height: 84pt, fill: red, stroke: none))
#place(top + left, dx: 200pt, dy: 168pt, rect(width: 100pt, height: 84pt, fill: blue, stroke: none))
"""
    guide = """#set page(width: 960pt, height: 540pt, margin: 0pt)
#place(top + left, dx: 96pt, dy: 54pt, rect(width: 192pt, height: 108pt, fill: red, stroke: none))
#place(top + left, dx: 384pt, dy: 216pt, rect(width: 192pt, height: 108pt, fill: blue, stroke: none))
"""
    _pdf(brand, "materials/examples/deck.pdf", deck)
    _pdf(brand, "materials/examples/report.pdf", doc)
    _pdf(brand, "materials/guidelines/book.pdf", guide)
    intake.take_in(brand)
    pages.parse_pdfs(brand)
    return brand


def _format(report, name):
    return next(item for item in report.formats if item.format == name)


def test_D1_classifies_vector_marks(tmp_path):
    brand = _fixture(tmp_path)
    report = vectors.measure_vectors(brand)
    page = next(p for p in report.pages if p.file == "materials/examples/deck.pdf" and p.page == 1)
    marks = page.marks
    assert any(
        m.kind == "rule"
        and m.orientation == "horizontal"
        and m.width == 1.0
        and m.width_assumed is True
        and m.colour == "#0B5FFF"
        for m in marks
    )
    assert any(m.kind == "rule" and m.width == 0.5 and m.width_assumed is False for m in marks)
    assert any(m.kind == "rule" and m.shape == "rect" and m.width == 2 and m.colour == "#111111" for m in marks)
    assert any(m.kind == "fill" and m.colour == "#E4002B" for m in marks)
    assert any(m.kind == "fill" and m.shape == "curve" and m.colour == "#00A651" for m in marks)
    assert any(m.kind == "stroke" and m.shape == "rect" and m.width == 3 for m in marks)
    assert any(m.kind == "fill" and m.colour == "#F5F5F5" and m.background for m in marks)


def test_D2_independent_format_grids_prefer_examples(tmp_path):
    brand = _fixture(tmp_path)
    report = vectors.measure_vectors(brand)
    slides = _format(report, "slides").grid
    assert slides is not None
    assert (slides.columns, slides.rows, slides.width, slides.height, slides.pages, slides.roles) == (
        20,
        12,
        960,
        540,
        2,
        ["examples"],
    )
    assert slides.unit_w == pytest.approx(48, abs=0.01)
    assert slides.unit_h == pytest.approx(45, abs=0.01)
    assert slides.x_score >= 0.9 and slides.y_score >= 0.9
    doc = _format(report, "doc").grid
    assert doc is not None
    assert (doc.columns, doc.rows) == (12, 20)
    assert doc.unit_w == pytest.approx(50, abs=0.01)
    assert doc.unit_h == pytest.approx(42, abs=0.01)


def test_D3_guidelines_fallback_and_sparse_edges(tmp_path):
    brand = _fixture(tmp_path)
    (brand / "materials/examples/deck.pdf").unlink()
    intake.take_in(brand)
    index = pages.parse_pdfs(brand)
    report = vectors.measure_vectors(brand)
    grid = _format(report, "slides").grid
    assert grid is not None
    assert (grid.roles, grid.columns, grid.rows) == (["guidelines"], 10, 10)
    assert vectors.unit_grid([], index, "slides") is None
    _require(vectors, "PageVectors", "VectorMark")
    sparse = vectors.PageVectors(
        file="sparse.pdf",
        page=1,
        role="examples",
        format="slides",
        width=960,
        height=540,
        marks=[vectors.VectorMark(kind="fill", shape="rect", x0=48, y0=45, x1=96, y1=90, colour="#000000")],
    )
    sparse_grid = vectors.unit_grid([sparse], pages.PageIndex(pages=[], skipped=[]), "slides")
    assert sparse_grid is not None
    assert sparse_grid.columns is None and sparse_grid.x_score == 0


def test_D4_tallies_and_deterministic_serialisation(tmp_path):
    brand = _fixture(tmp_path)
    (brand / "materials/guidelines/book.pdf").unlink()
    intake.take_in(brand)
    pages.parse_pdfs(brand)
    report = vectors.measure_vectors(brand)
    tallies = _format(report, "slides").tallies
    red = next(t for t in tallies if t.kind == "fill" and t.colour == "#E4002B")
    assert red.count == 2
    assert red.area_share == pytest.approx((2 * 144 * 90) / (2 * 960 * 540), abs=0.0001)
    assert any(t.kind == "rule" and t.colour == "#111111" and t.width == 2.0 for t in tallies)
    path = brand / "theme/ingest/vectors.json"
    before = path.read_bytes()
    assert vectors.VectorReport.model_validate_json(before) == report
    vectors.measure_vectors(brand)
    assert path.read_bytes() == before


def test_D5_command_records_change_and_requires_index(tmp_path, capsys):
    _require(changes, "change_log")
    brand = _fixture(tmp_path)
    run_git(brand, "add", "-A")
    run_git(brand, "commit", "-m", "Add indexed materials")
    assert cli.main(["brand", "vectors", "acme", "--root", str(brand.parent)]) == 0
    output = capsys.readouterr().out
    assert any("slides" in line and "20 x 12" in line and "48.0 x 45.0" in line for line in output.splitlines())
    assert run_git(brand, "branch", "--show-current").strip() == "main"
    assert run_git(brand, "status", "--porcelain") == ""
    assert any(record.what == "Measure the PDFs' vector data" for record in changes.change_log(brand))
    other = init_brand("other", brand.parent)
    assert cli.main(["brand", "vectors", "other", "--root", str(brand.parent)]) == 2
    assert run_git(other, "status", "--porcelain") == ""
