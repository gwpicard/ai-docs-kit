# Intent: Capture a brand's signature graphic as traced, measured data.
import importlib
import importlib.util
import hashlib
import shutil

import pytest

from ai_docs_kit import cli
from ai_docs_kit.brand.git import run_git
from ai_docs_kit.brand.workspace import BrandError, init_brand
from ai_docs_kit.render.typst import compile_pdf
from ai_docs_kit.theme import NEUTRAL_ROOT

try:
    graphic = importlib.import_module("ai_docs_kit.brand.graphic")
except ImportError as error:
    if error.name != "ai_docs_kit.brand.graphic" or importlib.util.find_spec("ai_docs_kit.brand.graphic") is not None:
        raise
    graphic = None


def require(*names):
    assert graphic is not None, "ai_docs_kit.brand.graphic must exist"
    for name in names:
        assert hasattr(graphic, name), f"ai_docs_kit.brand.graphic.{name} must exist"
    return graphic


def grid():
    from ai_docs_kit.brand.vectors import UnitGrid

    return UnitGrid(format="slides", width=960, height=540, pages=2, roles=["examples"],
                    columns=20, rows=12, unit_w=48, unit_h=45, x_score=1, y_score=1)


def tiles():
    g = require("Tile")
    return [g.Tile(col=2, row=2, cols=3, rows=2, colour="#2F5D8A", role="accent"),
            g.Tile(col=5, row=2, cols=1, rows=1, colour="#1A1A1A", role="ink")]


def rect(x, y, w, h, colour):
    return f'#place(top + left, dx: {x}pt, dy: {y}pt, rect(width: {w}pt, height: {h}pt, fill: rgb("{colour}"), stroke: none))\n'


def make_brand(tmp_path):
    root = tmp_path / ".brand"
    path = init_brand("acme", root)
    shutil.copytree(NEUTRAL_ROOT, path / "theme", dirs_exist_ok=True)
    run_git(path, "add", "-A")
    run_git(path, "commit", "-m", "Install neutral theme")

    def pdf(name, source):
        target = path / name
        source_path = target.with_suffix(".typ")
        source_path.write_text(source, encoding="utf-8")
        compile_pdf(source_path, path, target)
        source_path.unlink()

    header = '#set page(width: 960pt, height: 540pt, margin: 0pt)\n'
    deck = "".join(rect(x, y, 48, 45, "#2F5D8A") for x, y in [(48, 45), (144, 135), (240, 225), (336, 315)])
    pdf("materials/examples/deck.pdf", header + deck + '#pagebreak()\n' + deck)
    first = (rect(0, 0, 960, 540, "#FFFFFF") + rect(96, 90, 144, 90, "#2F5D8A")
             + rect(240, 90, 48, 45, "#1A1A1A") + rect(333, 211, 17, 23, "#2F5D8A")
             + rect(480, 135, 240, 2, "#1A1A1A")
             + '#place(top + left, dx: 480pt, dy: 270pt, ellipse(width: 96pt, height: 90pt, fill: rgb("#2F5D8A"), stroke: none))\n')
    second = rect(480, 180, 96, 90, "#2F5D8A") + rect(672, 315, 48, 45, "#1A1A1A")
    third = rect(720, 360, 96, 45, "#2F5D8A")
    pdf("materials/guidelines/book.pdf", header + first + '#pagebreak()\n' + second + '#pagebreak()\n' + third + '#pagebreak()\nText')
    pdf("materials/examples/report.pdf", '#set page(paper: "a4", margin: 0pt)\nReport')
    for command in ("intake", "parse", "vectors"):
        assert cli.main(["brand", command, "acme", "--root", str(root)]) == 0
    return path


def test_D1_trace_filled_shapes(tmp_path):
    g = require("trace_pdf_page")
    brand = make_brand(tmp_path)
    actual, untraced = g.trace_pdf_page(brand / "materials/guidelines/book.pdf", 1, grid(),
                                       {"ink": "#1A1A1A", "dark": "#1A1A1A", "accent": "#2F5D8A"})
    assert actual == tiles()
    assert untraced == 2


def test_D2_measure_and_corner_connectivity():
    g = require("measure", "Tile")
    result = g.measure(tiles(), grid())
    assert (result.coverage, result.tiles, result.clusters) == (0.0292, 2, 1)
    assert result.regions == [0.25, 0, 0, 0, 0, 0, 0, 0, 0]
    assert (result.margin_cols, result.margin_rows) == (2, 2)
    assert result.sizes == [(1, 1), (3, 2)]
    assert result.colours == ["#1A1A1A", "#2F5D8A"]
    corner = [g.Tile(col=0, row=0, cols=1, rows=1, colour="#1A1A1A", role=None),
              g.Tile(col=1, row=1, cols=1, rows=1, colour="#1A1A1A", role=None)]
    assert g.measure(corner, grid()).clusters == 2


def test_D3_trace_graphic_and_range(tmp_path):
    g = require("trace_graphic")
    brand = make_brand(tmp_path)
    name = "materials/guidelines/book.pdf"
    result = g.trace_graphic(brand, [(name, 1), (name, 2), (name, 3)])
    assert result.format == "slides"
    assert (result.grid.columns, result.grid.rows, result.grid.unit_w, result.grid.unit_h) == (20, 12, 48, 45)
    digest = hashlib.sha256((brand / name).read_bytes()).hexdigest()
    assert [(p.file, p.page, p.sha256) for p in result.pages] == [(name, 1, digest), (name, 2, digest), (name, 3, digest)]
    assert len(result.signatures) == 3
    assert result.range.coverage == (0.0083, 0.0292)
    assert result.range.tiles == (1, 2)
    assert result.range.clusters == (1, 2)
    assert result.range.regions_max == [0.25, 0, 0, 0, 0.1429, 0.0417, 0, 0, 0.0833]
    assert result.range.margin_cols == 2
    assert result.range.margin_rows == 2
    assert result.range.sizes == [(1, 1), (2, 1), (2, 2), (3, 2)]
    assert result.range.colours == ["#1A1A1A", "#2F5D8A"]


def test_D4_reject_invalid_traces(tmp_path):
    g = require("trace_graphic")
    brand = make_brand(tmp_path)
    name = "materials/guidelines/book.pdf"
    for pages in ([], [(name, 1), ("materials/examples/report.pdf", 1)], [(name, 4)],
                  [("materials/guidelines/missing.pdf", 1)], [(name, 9)]):
        with pytest.raises(BrandError):
            g.trace_graphic(brand, pages)
    (brand / "theme/ingest/vectors.json").unlink()
    with pytest.raises(BrandError, match="ai_docs_kit brand vectors"):
        g.trace_graphic(brand, [(name, 1)])


def test_D5_cli_saves_and_commits_without_recording_failure(tmp_path, capsys):
    g = require("trace_graphic", "load_graphic")
    brand = make_brand(tmp_path)
    name = "materials/guidelines/book.pdf"
    expected = g.trace_graphic(brand, [(name, 1), (name, 2), (name, 3)])
    args = ["brand", "graphic", "acme", "--root", str(brand.parent)]
    capsys.readouterr()
    assert cli.main(args + ["--trace", f"{name}:1", "--trace", f"{name}:2", "--trace", f"{name}:3"]) == 0
    output = capsys.readouterr().out
    assert "book.pdf p1" in output and "2 tiles" in output
    assert g.load_graphic(brand) == expected
    assert (brand / "theme/graphics/signature.yaml").is_file()
    assert run_git(brand, "branch", "--show-current").strip() == "main"
    assert run_git(brand, "status", "--porcelain").strip() == ""
    head = run_git(brand, "rev-parse", "HEAD")
    assert cli.main(args + ["--trace", f"{name}:9"]) == 2
    assert run_git(brand, "rev-parse", "HEAD") == head
    assert g.load_graphic(brand) == expected
