# Show every doctype component in the brand's theme before a real report exists.
import importlib.util
import shutil
from pathlib import Path

import pytest
import yaml
from PIL import Image

from ai_docs_kit.brand.git import run_git
from ai_docs_kit.brand.workspace import init_brand
from ai_docs_kit.cli import main
from ai_docs_kit.doctypes import load_doctypes
from ai_docs_kit.facts.pdf import PdfPlumberFacts
from ai_docs_kit.render.components import all_manifests
from ai_docs_kit.render.compose import compose

try:
    import ai_docs_kit.brand.specimen as specimen
except ImportError as error:
    if error.name != "ai_docs_kit.brand.specimen" and not (
        error.name and error.name.startswith("ai_docs_kit.brand.specimen.")
        and importlib.util.find_spec(error.name) is None
    ):
        raise
    specimen = None


@pytest.fixture(scope="module")
def brand(tmp_path_factory):
    root = tmp_path_factory.mktemp("specimen") / ".brand"
    path = init_brand("acme", root)
    neutral = Path(__file__).resolve().parents[2] / "src/ai_docs_kit/themes/neutral"
    shutil.copytree(neutral, path / "theme", dirs_exist_ok=True)
    tokens_path = path / "theme/tokens.yaml"
    tokens = yaml.safe_load(tokens_path.read_text())
    tokens["type"]["families"]["display"] = {
        "name": "Inter", "files": ["Inter-Regular.ttf", "Inter-SemiBold.ttf"]
    }
    tokens["colour"]["roles"]["ink"] = "#14213D"
    tokens_path.write_text(yaml.safe_dump(tokens, sort_keys=False))
    run_git(path, "add", "-A")
    run_git(path, "commit", "-m", "Set specimen theme")
    return path


@pytest.fixture(scope="module")
def deck(brand):
    if specimen is None or not hasattr(specimen, "render_specimen"):
        return None
    return specimen.render_specimen(brand, load_doctypes()["pitch-deck"])


def test_D1_specimen_documents_cover_each_component():
    assert specimen is not None and hasattr(specimen, "specimen_document"), "specimen_document must exist"
    manifests = all_manifests()
    types = load_doctypes()
    for name, fmt in [("pitch-deck", "slides"), ("report", "doc")]:
        doc = specimen.specimen_document(types[name])
        components = [section.component for section in doc.sections]
        expected = {name for name, manifest in manifests.items() if manifest.format == fmt}
        assert doc.format == fmt
        assert set(components) == expected
        assert len(components) == len(expected)
        if fmt == "slides":
            assert components[0] == "cover"
            assert components[-1] == "closing"
            assert [section.component for section in compose(doc).sections] == components


def test_D2_deck_pages_sheet_and_clean_brand(brand, deck):
    assert specimen is not None and hasattr(specimen, "SpecimenRender"), "SpecimenRender must exist"
    assert deck is not None, "render_specimen must exist"
    doc = specimen.specimen_document(load_doctypes()["pitch-deck"])
    folder = Path(deck.folder)
    assert not folder.is_absolute()
    assert folder.parts[:5] == ("theme", "ingest", "work", "specimens", "pitch-deck")
    facts = PdfPlumberFacts().extract(brand / deck.pdf)
    assert len(facts) == len(doc.sections) == len(deck.pages)
    for index, (page, fact, section) in enumerate(zip(deck.pages, facts, doc.sections), 1):
        assert page.page == index
        assert (fact.width, fact.height) == pytest.approx((960, 540), abs=0.5)
        assert page.components == [section.component]
        with Image.open(brand / page.png) as image:
            assert image.format == "PNG"
    with Image.open(brand / deck.sheet) as image:
        assert image.format == "PNG"
        assert max(image.size) <= 1568
    assert specimen.SpecimenRender.model_validate_json((brand / folder / "specimen.json").read_text()) == deck
    assert run_git(brand, "status", "--porcelain") == ""


def test_D3_theme_and_content_addressed_cache(brand, deck):
    assert specimen is not None and hasattr(specimen, "specimen_for"), "specimen_for must exist"
    assert deck is not None, "render_specimen must exist"
    facts = PdfPlumberFacts().extract(brand / deck.pdf)
    words = [word for page in facts for word in page.words]
    assert words
    assert all("Serif" not in word.font for word in words)
    assert any(word.colour == "#14213D" for word in words)
    before = (brand / deck.pdf).stat().st_mtime_ns
    again = specimen.render_specimen(brand, load_doctypes()["pitch-deck"])
    assert again.folder == deck.folder
    assert (brand / deck.pdf).stat().st_mtime_ns == before
    tokens_path = brand / "theme/tokens.yaml"
    original = tokens_path.read_text()
    try:
        tokens = yaml.safe_load(original)
        tokens["pages"]["slides"]["margin"]["left"] = "45pt"
        tokens_path.write_text(yaml.safe_dump(tokens, sort_keys=False))
        changed = specimen.render_specimen(brand, load_doctypes()["pitch-deck"])
        assert changed.folder != deck.folder
        assert specimen.specimen_for(brand, "pitch-deck") == changed
    finally:
        tokens_path.write_text(original)


def test_D4_report_a4_and_component_pages(brand):
    assert specimen is not None and hasattr(specimen, "component_pages"), "component_pages must exist"
    assert hasattr(specimen, "render_specimen"), "render_specimen must exist"
    render = specimen.render_specimen(brand, load_doctypes()["report"])
    facts = PdfPlumberFacts().extract(brand / render.pdf)
    assert len(facts) == len(render.pages) > 0
    for fact, page in zip(facts, render.pages):
        assert (fact.width, fact.height) == pytest.approx((595.28, 841.89), abs=0.5)
        assert page.components
    pages = specimen.component_pages(render)
    for component in ("body", "callout"):
        assert component in pages
        assert pages[component] == next(page.page for page in render.pages if component in page.components)


def test_D5_cli_renders_and_reports_errors(brand, deck, tmp_path, capsys):
    assert specimen is not None and hasattr(specimen, "render_specimen"), "render_specimen must exist"
    assert deck is not None
    root = brand.parent
    assert main(["brand", "specimen", "acme", "--root", str(root), "--doctype", "pitch-deck"]) == 0
    output = capsys.readouterr()
    assert any(line.startswith("pitch-deck") and deck.sheet in line for line in output.out.splitlines())
    empty_root = tmp_path / ".brand"
    init_brand("new", empty_root)
    assert main(["brand", "specimen", "new", "--root", str(empty_root)]) == 2
    assert "tokens.yaml" in capsys.readouterr().err
    assert main(["brand", "specimen", "acme", "--root", str(root), "--doctype", "nosuch"]) == 2
    assert "nosuch" in capsys.readouterr().err
