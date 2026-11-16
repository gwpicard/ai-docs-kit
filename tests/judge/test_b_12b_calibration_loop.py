# Turn comparison differences into a reviewable, bounded calibration run.
import asyncio
import importlib
import importlib.util
import json
import shutil

import pytest
import yaml

import ai_docs_kit.cli
from ai_docs_kit.agents.client import Claude
from ai_docs_kit.agents.ledger import Ledger
from ai_docs_kit.brand.workspace import init_brand
from ai_docs_kit.config import Price
from ai_docs_kit.doctypes import Doctype, load_doctypes
from ai_docs_kit.render.typst import compile_pdf
from ai_docs_kit.testing.fakes import FakeTransport, fake_response
from ai_docs_kit.theme import NEUTRAL_ROOT, load_theme


def optional_module(name):
    try:
        return importlib.import_module(name)
    except ImportError as error:
        if error.name != name and not str(error.name).startswith(name + "."):
            raise
        if importlib.util.find_spec(name) is not None:
            raise
        return None


calibration = optional_module("ai_docs_kit.brand.calibrate")
roles = optional_module("ai_docs_kit.brand.roles")


def make_brand(tmp_path):
    assert calibration is not None, "ai_docs_kit.brand.calibrate must exist"
    for name in ("calibrate_brand", "load_run", "save_run"):
        assert hasattr(calibration, name), f"calibrate.{name} must exist"
    assert roles is not None and hasattr(roles, "set_roles"), "roles.set_roles must exist"
    root = tmp_path / ".brand"
    path = init_brand("acme", root)
    shutil.copytree(NEUTRAL_ROOT, path / "theme", dirs_exist_ok=True)
    tokens = path / "theme" / "tokens.yaml"
    data = yaml.safe_load(tokens.read_text())
    data["type"]["families"]["display"] = {"name": "Inter", "files": ["Inter-Regular.ttf", "Inter-SemiBold.ttf"]}
    tokens.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    for folder, name, size, count in (
        ("guidelines", "book", "width: 960pt, height: 540pt", 3),
        ("examples", "report", 'paper: "a4"', 2),
    ):
        source = tmp_path / f"{name}.typ"
        source.write_text(f"#set page({size})\n" + "#pagebreak()\n".join(["Example"] * count))
        compile_pdf(source, tmp_path, path / "materials" / folder / f"{name}.pdf")
    assert ai_docs_kit.cli.main(["brand", "intake", "acme", "--root", str(root)]) == 0
    assert ai_docs_kit.cli.main(["brand", "parse", "acme", "--root", str(root)]) == 0
    roles.set_roles(
        path,
        [
            ("materials/guidelines/book.pdf", 2, "cover"),
            ("materials/examples/report.pdf", 1, "body"),
        ],
    )
    return path


def doctype(name):
    original = load_doctypes()[name]
    if name == "pitch-deck":
        data = original.model_dump(by_alias=True)
        data["outline"] = [{"section": "opener", "intent": "cover"}]
        return Doctype.model_validate(data)
    return original


def difference(value=None, *, area="margins", says="The left margin is wider.", token="pages.slides.margin.left"):
    return {
        "area": area,
        "says": says,
        "brand_box": None,
        "specimen_box": None,
        "change": None if value is None else {"token": token, "value": value},
    }


def run(brand, replies, *, name="pitch-deck", max_rounds=None):
    transport = FakeTransport(
        {"calibrate-model": [fake_response(json.dumps({"differences": items})) for items in replies]}
    )
    ledger = Ledger(brand / "usage.jsonl", {"calibrate-model": Price(input=0, output=0)})
    claude = Claude(transport, ledger, {"calibrate": "calibrate-model"})
    options = {} if max_rounds is None else {"max_rounds": max_rounds}
    result = asyncio.run(calibration.calibrate_brand(claude, brand, doctype(name), **options))
    return result, transport


def test_D1_applies_and_persists_without_changing_brand(tmp_path):
    brand = make_brand(tmp_path)
    original = (brand / "theme/tokens.yaml").read_bytes()
    result, transport = run(brand, [[difference("64pt")], []])
    assert result.stopped == "no-differences"
    assert len(result.rounds) == len(transport.requests) == 2
    assert result.rounds[0].applied == [result.rounds[0].differences[0].id]
    assert result.rounds[0].specimen != result.rounds[1].specimen
    assert load_theme(brand / result.candidate).pages["slides"].margin.left == 64.0
    assert (brand / "theme/tokens.yaml").read_bytes() == original
    assert len(result.corrections) == 1
    correction = result.corrections[0]
    assert (correction.state, correction.before, correction.after, correction.round) == ("proposed", "40pt", "64pt", 1)
    assert (correction.component, correction.brand_page) == ("cover", 2)
    assert calibration.load_run(brand, "pitch-deck") == result


def test_D2_rolls_back_when_differences_grow(tmp_path):
    brand = make_brand(tmp_path)
    result, transport = run(
        brand, [[difference("64pt")], [difference(), difference(area="graphic", says="A shape differs.")]]
    )
    assert result.stopped == "differences-grew"
    assert len(result.rounds) == len(transport.requests) == 2
    assert [c.state for c in result.corrections] == ["dropped"]
    assert load_theme(brand / result.candidate).pages["slides"].margin.left == 40.0
    assert result.remaining == result.rounds[0].differences


def test_D3_limits_rounds_and_supersedes_corrections(tmp_path):
    brand = make_brand(tmp_path)
    replies = [[difference(value, says=f"Margin is {value}.")] for value in ("52pt", "56pt", "60pt", "64pt")]
    result, transport = run(brand, replies)
    assert result.stopped == "max-rounds"
    assert len(transport.requests) == len(result.rounds) == 4
    assert load_theme(brand / result.candidate).pages["slides"].margin.left == 60.0
    assert [d.after for d in result.remaining] == ["64pt"]
    assert [c.state for c in result.corrections] == ["superseded", "superseded", "proposed"]
    assert (result.corrections[2].before, result.corrections[2].after, result.corrections[2].round) == (
        "40pt",
        "60pt",
        3,
    )
    limited, transport = run(brand, replies, max_rounds=2)
    assert limited.stopped == "max-rounds"
    assert len(transport.requests) == len(limited.rounds) == 2


def test_D4_stops_for_unchangeable_differences_and_no_pairs(tmp_path):
    brand = make_brand(tmp_path)
    result, transport = run(brand, [[difference(area="graphic")]])
    assert result.stopped == "nothing-to-change"
    assert len(transport.requests) == 1
    assert result.corrections == []
    assert result.remaining == result.rounds[0].differences
    assert len(result.remaining) == 1 and result.remaining[0].area == "graphic"
    roles.set_roles(brand, [])
    result, transport = run(brand, [])
    assert result.stopped == "no-pairs"
    assert result.rounds == [] and transport.requests == []


def test_D5_carries_and_filters_rejected_corrections(tmp_path):
    brand = make_brand(tmp_path)
    first, _ = run(brand, [[difference("64pt")], []])
    saved = calibration.load_run(brand, "pitch-deck")
    assert saved == first
    saved.corrections[0].state = "rejected"
    calibration.save_run(brand, saved)
    result, transport = run(brand, [[difference("64pt")]])
    assert len(transport.requests) == 1
    request = json.dumps(transport.requests[0])
    assert "REJECTED BY THE PERSON" in request and first.corrections[0].says in request
    assert result.stopped == "no-differences" and result.remaining == []
    assert len(result.corrections) == 1 and result.corrections[0].state == "rejected"


def test_D6_report_format_and_unknown_doctype(tmp_path):
    brand = make_brand(tmp_path)
    result, transport = run(brand, [[difference("25mm", token="pages.doc.margin.left")], []], name="report")
    assert result.stopped == "no-differences" and len(transport.requests) == 2
    assert len(result.corrections) == 1
    correction = result.corrections[0]
    assert (correction.format, correction.before, correction.after) == ("doc", "20mm", "25mm")
    assert load_theme(brand / result.candidate).pages["doc"].margin.left == pytest.approx(25 * 72 / 25.4)
    assert ai_docs_kit.cli.main(["brand", "calibrate", "acme", "--root", str(brand.parent), "--doctype", "nosuch"]) == 2
