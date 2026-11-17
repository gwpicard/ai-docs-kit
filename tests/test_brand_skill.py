import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
import yaml

from ai_docs_kit.render.typst import compile_pdf

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "brand" / "SKILL.md"
NEUTRAL_FONTS = ROOT / "src/ai_docs_kit/themes/neutral/fonts"
BRAND_COMMAND = re.compile(r"ai-docs-kit brand ([a-z][a-z0-9-]*)")
STEPS = ("intake", "measure", "synthesise", "specimen")


def skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


def run(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "ai_docs_kit.cli", *args], capture_output=True, text=True, cwd=cwd)


def test_skill_is_no_longer_a_stub():
    assert "Stub." not in skill_text()


@pytest.mark.parametrize("step", STEPS)
def test_skill_names_each_brand_step(step):
    assert step in set(BRAND_COMMAND.findall(skill_text()))


def test_skill_names_the_theme_build():
    assert re.search(r"ai-docs-kit build [^`\n]*--theme", skill_text())


def test_skill_names_the_questions_for_inferred_values():
    text = skill_text()
    assert "Inferred" in text
    assert re.search(r"question", text, re.IGNORECASE)


def test_skill_forbids_inventing_values():
    assert re.search(r"never invent|do not invent|not invent", skill_text(), re.IGNORECASE)


def test_skill_keeps_brand_material_out_of_the_repository():
    assert re.search(r"repository", skill_text(), re.IGNORECASE)


def example_pdf(path: Path, work: Path) -> None:
    source = work / "input.typ"
    source.write_text(
        "#set page(width: 960pt, height: 540pt, margin: (top: 40pt, bottom: 40pt, left: 48pt, right: 48pt))\n"
        '#set text(font: "Inter", size: 20pt, fill: rgb("#101820"))\n'
        "A synthetic title\n\nThis is a body line with enough words.\\\nThis is another body line with words.\n"
        '#place(bottom, rect(width: 100%, height: 4pt, fill: rgb("#0B5FFF")))\n',
        encoding="utf-8",
    )
    compile_pdf(source, work, path, [NEUTRAL_FONTS])


def template_pptx(path: Path) -> None:
    """A PowerPoint template whose theme names Inter, the one typeface the brand folder ships."""
    from pptx import Presentation

    Presentation().save(path)
    with zipfile.ZipFile(path) as source:
        parts = {item.filename: source.read(item.filename) for item in source.infolist()}
    for name, content in parts.items():
        if name.startswith("ppt/theme/"):
            parts[name] = content.replace(b'typeface="Calibri Light"', b'typeface="Inter"').replace(
                b'typeface="Calibri"', b'typeface="Inter"'
            )
    with zipfile.ZipFile(path, "w") as target:
        for name, content in parts.items():
            target.writestr(name, content)


def test_commands_the_skill_names_turn_a_synthetic_pack_into_a_theme_that_builds(tmp_path):
    root = tmp_path / "brands"
    assert run("brand", "init", "acme", "--root", str(root), cwd=tmp_path).returncode == 0
    brand = root / "acme"
    example_pdf(brand / "materials/examples/deck.pdf", tmp_path)
    labels = {
        "typefaces": ["Inter"],
        "fonts": [
            {"file": f"Inter-{name}.ttf", "family": "Inter", "weight": weight, "licence": "OFL-1.1"}
            for name, weight in (("Regular", 400), ("SemiBold", 600))
        ],
    }
    (brand / "materials/fonts/fonts.yaml").write_text(yaml.safe_dump(labels), encoding="utf-8")
    template_pptx(brand / "materials/templates/brand.pptx")
    for font in NEUTRAL_FONTS.glob("Inter-*.ttf"):
        shutil.copy(font, brand / "materials/fonts" / font.name)
    for step in ("intake", "fonts", "templates", "parse", "measure", "reconcile", "synthesise", "specimen"):
        done = run("brand", step, "acme", "--root", str(root), cwd=tmp_path)
        assert done.returncode == 0, f"{step}: {done.stderr}{done.stdout}"
    theme = brand / "theme"
    assert yaml.safe_load((theme / "tokens.yaml").read_text(encoding="utf-8"))
    working = tmp_path / "doc.md"
    gallery = (ROOT / "tests/fixtures/slides/gallery.md").read_text(encoding="utf-8")
    working.write_text(gallery.split("::: {#quote")[0], encoding="utf-8")
    built = run("build", str(working), "--theme", str(theme), "--out", str(tmp_path / "out"), cwd=tmp_path)
    assert built.returncode == 0, built.stderr + built.stdout
    assert list((tmp_path / "out").rglob("*.pdf"))
