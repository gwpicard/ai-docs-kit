import shutil

import pytest
import yaml

from ai_docs_kit.brand.git import run_git
from ai_docs_kit.brand.workspace import init_brand
from ai_docs_kit.cli import main
from ai_docs_kit.theme import NEUTRAL_ROOT

INFERRED = {"label": "inferred", "source": {"note": "Neutral theme judgement"}}
TOKENS = [
    "colour.roles",
    "colour.chart",
    "colour.usage",
    "colour.contrast_min",
    "type.families",
    "type.scale",
    "pages.slides",
    "pages.doc",
    "spacing.unit",
    "spacing.scale",
    "imagery.min_dpi",
]


def _brand(tmp_path):
    brand = init_brand("acme", tmp_path / ".brand")
    theme = brand / "theme"
    shutil.rmtree(theme)
    shutil.copytree(NEUTRAL_ROOT, theme)
    info = yaml.safe_load((theme / "theme.yaml").read_text())
    info["labelled"] = True
    (theme / "theme.yaml").write_text(yaml.safe_dump(info, sort_keys=False))
    items = yaml.safe_load((theme / "rubric/visual.yaml").read_text())["items"]
    provenance = {
        "tokens": {path: INFERRED for path in TOKENS},
        "rubric": {item["id"]: INFERRED for item in items},
    }
    (theme / "provenance.yaml").write_text(yaml.safe_dump(provenance, sort_keys=False))
    run_git(brand, "add", "-A")
    run_git(brand, "commit", "-m", "Add labelled theme")
    return brand


@pytest.mark.parametrize("reason", ["", "   "])
def test_brand_set_with_blank_reason_leaves_the_brand_on_main_and_clean(tmp_path, reason):
    brand = _brand(tmp_path)
    root = str(tmp_path / ".brand")
    bad = ["brand", "set", "acme", "pages.slides.margin.left", "52", "--reason", reason, "--root", root]
    assert main(bad) == 2
    assert run_git(brand, "branch", "--show-current").strip() == "main"
    assert run_git(brand, "status", "--porcelain").strip() == ""
    good = ["brand", "set", "acme", "pages.slides.margin.left", "53", "--reason", "Examples", "--root", root]
    assert main(good) == 0
