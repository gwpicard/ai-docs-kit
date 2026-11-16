# Intent: Brand doctypes extend and override packaged doctypes in theme-aware workflows.
import asyncio
import json
import shutil
from pathlib import Path

import pytest

try:
    import ai_docs_kit.doctypes as doctypes
    import ai_docs_kit.write as write
    from ai_docs_kit import cli
    from ai_docs_kit.model import Document, Section
    from ai_docs_kit.source.parser import parse
    from ai_docs_kit.theme import load_theme
except ImportError as error:
    if error.name not in {
        "ai_docs_kit.doctypes",
        "ai_docs_kit.write",
        "ai_docs_kit.cli",
        "ai_docs_kit.model",
        "ai_docs_kit.source.parser",
        "ai_docs_kit.theme",
    }:
        raise
    doctypes = write = cli = Document = Section = parse = load_theme = None

NEUTRAL = Path(__file__).resolve().parents[2] / "src/ai_docs_kit/themes/neutral"


def theme_copy(tmp_path):
    root = tmp_path / "theme"
    shutil.copytree(NEUTRAL, root)
    return root


def add_type(root, stem, outline, *, fmt="slides", name=None):
    folder = root / "doctypes"
    folder.mkdir(exist_ok=True)
    (folder / f"{stem}.yaml").write_text(
        f"name: {name or stem}\nformat: {fmt}\naudience: Test readers\n"
        f"length: {{{'slides' if fmt == 'slides' else 'pages'}: [1, 8]}}\n"
        "questions: []\noutline:\n" + outline + "checks: []\nchecklist: []\n"
    )


def quarterly(root):
    add_type(
        root,
        "quarterly",
        "  - section: opener\n    intent: statement\n    required: true\n"
        "  - section: content\n    intent: any\n    repeat: [1, 8]\n",
    )


def invoke(args, capsys):
    assert cli is not None and hasattr(cli, "main")
    try:
        code = cli.main(args)
    except SystemExit as error:
        code = error.code
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_D1_brand_types_merge_and_override(tmp_path):
    assert doctypes is not None and hasattr(doctypes, "doctypes_for") and hasattr(doctypes, "packaged_doctypes")
    root = theme_copy(tmp_path)
    quarterly(root)
    add_type(root, "memo", "  - section: intro\n    intent: body\n", fmt="doc")
    packaged = doctypes.packaged_dir() / "pitch-deck.yaml"
    (root / "doctypes/pitch-deck.yaml").write_text(
        packaged.read_text().replace("Decision makers who will act on the ask", "Brand readers")
    )
    types = doctypes.doctypes_for(root)
    assert {"quarterly", "memo", "pitch-deck", "report"} <= set(types)
    assert types["quarterly"].format == "slides"
    assert [entry.section for entry in types["quarterly"].outline] == ["opener", "content"]
    assert types["memo"].format == "doc"
    assert types["pitch-deck"].audience == "Brand readers"
    assert doctypes.packaged_doctypes()["pitch-deck"].audience == "Decision makers who will act on the ask"
    assert set(doctypes.load_doctypes()) == {"pitch-deck", "report"}


def test_D2_missing_brand_folder_and_library(tmp_path):
    assert doctypes is not None
    for name in ("doctypes_for", "packaged_doctypes", "load_brand_doctypes", "library_dir"):
        assert hasattr(doctypes, name), f"ai_docs_kit.doctypes.{name} must exist"
    root = theme_copy(tmp_path)
    assert doctypes.load_brand_doctypes(root) == {}
    assert doctypes.doctypes_for(root) == doctypes.packaged_doctypes()
    assert doctypes.doctypes_for() == doctypes.packaged_doctypes()
    assert doctypes.library_dir() == doctypes.packaged_dir() / "library"
    assert doctypes.library_dir().is_dir()


def test_D3_invalid_brand_types_fail_and_theme_test_reports_file(tmp_path, capsys):
    assert doctypes is not None and hasattr(doctypes, "doctypes_for")
    root = theme_copy(tmp_path)
    add_type(root, "broken", "  - section: dates\n    intent: timeline\n")
    with pytest.raises(doctypes.DoctypeError) as caught:
        doctypes.doctypes_for(root)
    assert "broken.yaml" in str(caught.value) and "timeline" in str(caught.value)
    code, out, err = invoke(["theme", "test", "--theme", str(root)], capsys)
    assert code == 1, (out, err)
    assert any(line.startswith("fail doctypes:") and "broken.yaml" in line for line in out.splitlines())
    (root / "doctypes/broken.yaml").unlink()
    add_type(root, "wrong", "  - section: intro\n    intent: statement\n", name="other")
    with pytest.raises(doctypes.DoctypeError, match="wrong.yaml"):
        doctypes.doctypes_for(root)
    (root / "doctypes/wrong.yaml").unlink()
    code, out, err = invoke(["theme", "test", "--theme", str(root)], capsys)
    assert code == 0, (out, err)
    assert out.splitlines()[2] == "ok doctypes"


def test_D4_write_uses_brand_doctype_for_outline(tmp_path):
    assert write is not None and hasattr(write, "run_write") and hasattr(write, "Agents")
    assert load_theme is not None and Document is not None and Section is not None and parse is not None
    root = theme_copy(tmp_path)
    quarterly(root)
    deck = tmp_path / "deck.md"
    deck.write_text("---\ndoctype: quarterly\nformat: slides\ntitle: Readout\n---\n")
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "notes.txt").write_text("A useful fact.\n")
    seen = []

    async def gather(extracted):
        return []

    async def outline(facts, doctype, front, store):
        seen.append(doctype.name)
        return Document(
            front=front,
            format="slides",
            sections=[
                Section(intent="statement", title="Opening"),
                Section(intent="bullets", title="Details"),
            ],
        ), []

    def writer(facts, doc):
        raise AssertionError("outline review must not draft")

    agents = write.Agents(gather=gather, outline=outline, writer=writer)
    try:
        result = asyncio.run(
            write.run_write(deck, agents=agents, theme=load_theme(root), out=tmp_path / "out", approve=False)
        )
    except KeyError as error:
        raise AssertionError(f"brand doctype must be available to write: {error}") from None
    assert result == 0
    assert seen == ["quarterly"]
    doc, findings = parse(deck.read_text())
    assert not [finding for finding in findings if finding.severity == "error"]
    assert [(section.intent, section.title) for section in doc.sections] == [
        ("statement", "Opening"),
        ("bullets", "Details"),
    ]


def test_D5_outline_check_uses_brand_and_ignores_unknown(tmp_path, capsys):
    root = theme_copy(tmp_path)
    quarterly(root)
    for name in ("quarterly", "not-a-type"):
        source = tmp_path / f"{name}.md"
        source.write_text(
            f"---\ndoctype: {name}\nformat: slides\ntitle: Readout\n---\n\n"
            '::: {#abcde .section intent="bullets" section="content"}\n## Details\n\n- A point.\n:::\n'
        )
        out_dir = tmp_path / f"out-{name}"
        code, out, err = invoke(
            ["check", str(source), "--outline", "--theme", str(root), "--out", str(out_dir)], capsys
        )
        assert code in (0, 1), (out, err)
        findings = json.loads((out_dir / f"{name}.findings.json").read_text())
        outline_findings = [f for f in findings if f["rule_id"] == "source.outline-conforms"]
        if name == "quarterly":
            assert any("opener" in f["message"] for f in outline_findings)
        else:
            assert outline_findings == []
