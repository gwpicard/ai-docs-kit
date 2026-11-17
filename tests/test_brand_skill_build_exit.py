import shutil
from pathlib import Path

import yaml

from test_brand_skill import NEUTRAL_FONTS, ROOT, example_pdf, run, template_pptx


def test_build_with_the_synthetic_brand_exits_zero(tmp_path):
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
    working = tmp_path / "doc.md"
    gallery = (ROOT / "tests/fixtures/slides/gallery.md").read_text(encoding="utf-8")
    working.write_text(gallery.split("::: {#quote")[0], encoding="utf-8")
    built = run("build", str(working), "--theme", str(brand / "theme"), "--out", str(tmp_path / "out"), cwd=tmp_path)
    assert built.returncode == 0, built.stderr + built.stdout
    assert list(Path(tmp_path / "out").rglob("*.pdf"))
