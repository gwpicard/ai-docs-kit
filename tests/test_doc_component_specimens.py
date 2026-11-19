"""New document components remain available through the brand specimen command."""

import json
import shutil

import pytest

from ai_docs_kit.cli import main
from ai_docs_kit.theme import neutral_theme


@pytest.mark.parametrize("doctype", ["report", "pitch-deck"])
def test_brand_specimen_includes_document_lists_and_figures_without_breaking_slides(tmp_path, capsys, doctype):
    root = tmp_path / "brands"
    assert main(["brand", "init", "sample", "--root", str(root)]) == 0
    brand = root / "sample"
    shutil.copytree(neutral_theme().root, brand / "theme", dirs_exist_ok=True)
    capsys.readouterr()

    args = ["brand", "specimen", "sample", "--root", str(root), "--doctype", doctype]
    assert main(args) == 0
    assert doctype in capsys.readouterr().out
    records = list((brand / "theme/ingest/work/specimens" / doctype).glob("*/specimen.json"))
    assert len(records) == 1
    record = json.loads(records[0].read_text())
    components = {component for page in record["pages"] for component in page["components"]}
    if doctype == "report":
        assert {"bullet-list", "key-figures-strip"} <= components
    else:
        assert {"cover", "bullets", "key-figures"} <= components
        assert components.isdisjoint({"bullet-list", "key-figures-strip"})
    for page in record["pages"]:
        assert (brand / page["png"]).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    pdf = brand / record["pdf"]
    before = pdf.stat().st_mtime_ns
    assert main(args) == 0
    assert pdf.stat().st_mtime_ns == before
