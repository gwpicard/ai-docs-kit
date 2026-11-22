"""Issue 280 review: require the new forms while checking specimens and flow."""

import json
import shutil
from pathlib import Path

from docx import Document as WordDocument

from ai_docs_kit.cli import main
from ai_docs_kit.model import Document, Section
from ai_docs_kit.source.serialiser import serialise
from ai_docs_kit.theme import neutral_theme


def test_report_forms_and_slide_specimen_share_one_scenario(tmp_path, capsys):
    root = tmp_path / "brands"
    assert main(["brand", "init", "sample", "--root", str(root)]) == 0
    brand = root / "sample"
    shutil.copytree(neutral_theme().root, brand / "theme", dirs_exist_ok=True)
    capsys.readouterr()

    for doctype in ("report", "pitch-deck"):
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


def _build(tmp_path, capsys, section):
    doc = Document(
        front={"doctype": "report"},
        format="doc",
        sources=[{"key": "S1", "text": "Synthetic site register"}],
        sections=[section],
    )
    source = tmp_path / "report.md"
    source.write_text(serialise(doc), encoding="utf-8")
    assert main(["build", str(source)]) == 0
    version = Path(capsys.readouterr().out.strip().splitlines()[-1])
    facts = json.loads((version / "layout.json").read_text())
    page = neutral_theme().tokens.pages["doc"]
    for word in facts["words"]:
        box = word["box"]
        assert box["x0"] >= page.margin.left - 0.5
        assert box["x1"] <= page.width - page.margin.right + 0.5
        assert box["y0"] >= page.margin.top - 0.5
        assert box["y1"] <= page.height - page.margin.bottom + 0.5
    return version, facts


def test_key_figure_labels_wrap_within_their_columns(tmp_path, capsys):
    labels = [
        "Completion of the initial access route survey",
        "Sites with confirmed delivery arrangements",
        "Reports returned for a further technical review",
        "Reports issued after the final site inspection",
    ]
    section = Section(
        id="figures",
        intent="key-numbers",
        title="Key figures",
        items=[
            {"head": str(i), "body": label, "citations": [{"key": "S1", "locator": "p.5"}]}
            for i, label in enumerate(labels, 1)
        ],
    )
    version, facts = _build(tmp_path, capsys, section)
    assert len(facts["pages"]) == 1
    for i, label in enumerate(labels):
        mark = next(m for m in facts["marks"] if m.get("field") == f"items[{i}].body")
        words = [
            word
            for word in facts["words"]
            if word["role"] == "figure-caption"
            and mark["x"] <= (word["box"]["x0"] + word["box"]["x1"]) / 2 <= mark["x"] + mark["w"]
        ]
        assert " ".join(word["text"] for word in words) == label
        assert len({round(word["box"]["y0"], 1) for word in words}) >= 2
        assert all(
            mark["x"] - 0.5 <= word["box"]["x0"] < word["box"]["x1"] <= mark["x"] + mark["w"] + 0.5 for word in words
        )
    assert (version / "pages/p01.png").is_file()


def test_long_list_flows_across_pages_without_losing_items(tmp_path, capsys):
    items = [
        {
            "head": f"Visit {i}",
            "body": "Survey the access route and record the delivery arrangements for the next review.",
            "sub": [f"Retain the site sketch for visit {i}."],
            "citations": [{"key": "S1", "locator": f"p.{i}"}],
        }
        for i in range(1, 41)
    ]
    section = Section(id="visits", intent="bullets", title="Site visits", items=items)
    version, facts = _build(tmp_path, capsys, section)
    assert len(facts["pages"]) > 1
    text = " ".join(word["text"] for word in facts["words"] if word["section_id"] == "visits")
    positions = []
    for i in range(1, 41):
        item = f"Visit {i} Survey the access route"
        assert text.count(item) == 1
        positions.append(text.index(item))
        assert f"[S1 p.{i}]" in text
        assert f"Retain the site sketch for visit {i}." in text
    assert positions == sorted(positions)
    index = json.loads((version / "pages/pages.json").read_text())
    assert index["sections"]["visits"] == list(range(1, len(facts["pages"]) + 1))
    for page in index["sections"]["visits"]:
        assert (version / "pages" / f"p{page:02d}.png").is_file()
    paragraphs = WordDocument(str(version / "report.docx")).paragraphs
    bullets = [p.text for p in paragraphs if p.style.name.startswith("List")]
    assert len(bullets) == len(items)
    assert all(f"Visit {i}: Survey the access route" in text for i, text in enumerate(bullets, 1))
