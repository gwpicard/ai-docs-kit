# Intent: compare mapped brand pages with their specimens and retain actionable, validated differences.
import asyncio
import hashlib
import importlib
import importlib.util
import json
import re
import shutil
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from ai_docs_kit.agents.client import Claude
from ai_docs_kit.brand.workspace import init_brand
from ai_docs_kit.config import ProjectConfig
from ai_docs_kit.testing.fakes import FakeTransport, fake_response
from ai_docs_kit.write import role_models


def optional_subject(name):
    try:
        return importlib.import_module(name)
    except ImportError as error:
        missing = error.name or ""
        if (missing == name or name.startswith(missing + ".")) and importlib.util.find_spec(missing) is None:
            return None
        raise


calibration = optional_subject("ai_docs_kit.brand.calibrate")


def require(*names):
    assert calibration is not None, "ai_docs_kit.brand.calibrate must exist"
    for name in names:
        assert hasattr(calibration, name), f"ai_docs_kit.brand.calibrate.{name} must exist"


@pytest.fixture(scope="module")
def setup_brand(tmp_path_factory):
    from ai_docs_kit.brand.roles import set_roles
    from ai_docs_kit.brand.specimen import render_specimen

    from ai_docs_kit.cli import main
    from ai_docs_kit.doctypes import doctypes_for
    from ai_docs_kit.render.typst import compile_pdf

    root = tmp_path_factory.mktemp("calibration")
    brand = init_brand("acme", root / ".brand")
    shutil.copytree(Path("src/ai_docs_kit/themes/neutral"), brand / "theme", dirs_exist_ok=True)
    for relative, page_set, count in (
        ("guidelines/book.pdf", "width: 960pt, height: 540pt", 3),
        ("examples/report.pdf", 'paper: "a4"', 2),
    ):
        source = root / (Path(relative).stem + ".typ")
        source.write_text(f"#set page({page_set})\n" + "#pagebreak()\n".join(f"Page {i}" for i in range(count)))
        compile_pdf(source, root, brand / "materials" / relative)
    with zipfile.ZipFile(brand / "materials/templates/deck.pptx", "w") as deck:
        deck.writestr("[Content_Types].xml", "<Types/>")
        for page in (1, 2):
            deck.writestr(f"ppt/slides/slide{page}.xml", "<slide/>")
    assert main(["brand", "intake", "acme", "--root", str(root / ".brand")]) == 0
    assert main(["brand", "parse", "acme", "--root", str(root / ".brand")]) == 0
    set_roles(
        brand,
        [
            ("materials/guidelines/book.pdf", 2, "cover"),
            ("materials/examples/report.pdf", 1, "body"),
            ("materials/templates/deck.pptx", 1, "statement"),
        ],
    )
    doctypes = doctypes_for(brand / "theme")
    deck = render_specimen(brand, doctypes["pitch-deck"])
    report = render_specimen(brand, doctypes["report"])
    return brand, deck, report


class Ledger:
    def add(self, role, model, usage):
        pass


def difference(area, says, token=None, value=None):
    return {
        "area": area,
        "says": says,
        "brand_box": None,
        "specimen_box": None,
        "change": None if token is None else {"token": token, "value": value},
    }


def run_compare(brand, specimen, differences, rejected=None):
    transport = FakeTransport({"calibrate-model": [fake_response(json.dumps({"differences": differences}))]})
    claude = Claude(transport, Ledger(), {"calibrate": "calibrate-model"})
    result = asyncio.run(calibration.compare(claude, brand, specimen, rejected=rejected))
    return result, transport.requests


def texts(blocks):
    return "\n".join(block["text"] for block in blocks if block.get("type") == "text")


def test_D1_pairs_match_format_and_skip_templates(request):
    require("calibration_pairs")
    from ai_docs_kit.brand.specimen import component_pages

    brand, deck, report = request.getfixturevalue("setup_brand")
    pairs = calibration.calibration_pairs(brand, deck)
    assert len(pairs) == 1
    pair = pairs[0]
    assert (pair.component, pair.format, pair.brand_file, pair.brand_page) == (
        "cover",
        "slides",
        "materials/guidelines/book.pdf",
        2,
    )
    assert pair.specimen_page == component_pages(deck)["cover"]
    with Image.open(brand / pair.brand_png) as image:
        assert image.format == "PNG"
        assert abs(image.width - 1467) <= 1
    pairs = calibration.calibration_pairs(brand, report)
    assert len(pairs) == 1
    assert (pairs[0].component, pairs[0].format, pairs[0].brand_page) == ("body", "doc", 1)


def test_D2_request_contains_images_tokens_and_rejections(request):
    require("compare", "CalibrationReport", "calibrate_blocks")
    brand, deck, _ = request.getfixturevalue("setup_brand")
    result, requests = run_compare(brand, deck, [], ["Title too large (type.scale.slides.title.size)"])
    assert result == []
    assert len(requests) == 1
    req = requests[0]
    assert req["model"] == "calibrate-model"
    assert req["output_config"]["effort"] == "medium"
    content = req["messages"][0]["content"]
    assert sum(block["type"] == "image" for block in content) == 2
    text = texts(content)
    for value in (
        "materials/guidelines/book.pdf p2",
        "specimen cover",
        "pages.slides.margin.left = 40pt",
        "colour.roles.accent = #2F5D8A",
        "REJECTED BY THE PERSON",
        "Title too large (type.scale.slides.title.size)",
    ):
        assert value in text
    assert "pages.doc." not in text
    assert "margins" in texts(req["system"]) and "graphic" in texts(req["system"])
    assert req["system"][-1]["cache_control"] == {"type": "ephemeral"}


def test_D3_changes_and_no_change_preserve_theme(request):
    require("compare", "Difference")
    brand, deck, _ = request.getfixturevalue("setup_brand")
    tokens = brand / "theme/tokens.yaml"
    before = tokens.read_bytes()
    data = [
        difference("margins", "Left margin is wider.", "pages.slides.margin.left", "64pt"),
        difference("colour", "Accent is orange.", "colour.roles.accent", "#C2410C"),
        difference("graphic", "The brand uses a diagonal."),
    ]
    values, _ = run_compare(brand, deck, data)
    assert len(values) == 3
    assert [(d.area, d.component, d.format, d.brand_page) for d in values] == [
        ("margins", "cover", "slides", 2),
        ("colour", "cover", "slides", 2),
        ("graphic", "cover", "slides", 2),
    ]
    assert (values[0].token, values[0].before, values[0].after, values[0].refused) == (
        "pages.slides.margin.left",
        "40pt",
        "64pt",
        None,
    )
    assert (values[1].token, values[1].before, values[1].after) == ("colour.roles.accent", "#2F5D8A", "#C2410C")
    assert (values[2].token, values[2].before, values[2].after, values[2].refused) == (None, None, None, None)
    for value in values:
        expected = f"cover|materials/guidelines/book.pdf|2|{value.area}|{value.says}"
        assert value.id == hashlib.sha1(expected.encode()).hexdigest()[:12]
        assert re.fullmatch(r"[0-9a-f]{12}", value.id)
    assert len({d.id for d in values}) == 3
    assert tokens.read_bytes() == before


def test_D4_invalid_changes_are_kept_and_refused(request):
    require("compare", "TokenChange", "check_change")
    brand, deck, _ = request.getfixturevalue("setup_brand")
    data = [
        difference("margins", "Middle margin differs.", "pages.slides.margin.middle", "64pt"),
        difference("colour", "Accent differs.", "colour.roles.accent", "blue"),
        difference("hierarchy", "Family differs.", "type.families", "Inter"),
        difference("margins", "Document margin differs.", "pages.doc.margin.left", "25mm"),
    ]
    values, _ = run_compare(brand, deck, data)
    assert len(values) == 4
    for value in values:
        assert (value.token, value.before, value.after) == (None, None, None)
        assert isinstance(value.refused, str) and value.refused
    assert "pages.slides.margin.middle" in values[0].refused
    assert (
        calibration.check_change(
            brand / "theme", "slides", calibration.TokenChange(token="type.scale.slides.title.size", value="28")
        )
        is None
    )


def test_D5_document_tokens_and_default_model(request):
    require("compare")
    brand, _, report = request.getfixturevalue("setup_brand")
    values, requests = run_compare(
        brand, report, [difference("margins", "Left margin is wider.", "pages.doc.margin.left", "25mm")]
    )
    assert len(requests) == 1
    content = texts(requests[0]["messages"][0]["content"])
    assert "pages.doc.margin.left = 20mm" in content
    assert "pages.slides." not in content
    assert len(values) == 1
    assert (values[0].format, values[0].token, values[0].before, values[0].after) == (
        "doc",
        "pages.doc.margin.left",
        "20mm",
        "25mm",
    )
    assert role_models(ProjectConfig())["calibrate"] == "claude-opus-5-5"
