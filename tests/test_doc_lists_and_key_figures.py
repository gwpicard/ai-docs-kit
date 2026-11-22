"""Issue 280: document lists and key figures through the build and check commands."""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest
import yaml
from docx import Document as WordDocument
from lxml import etree

from ai_docs_kit.cli import main
from ai_docs_kit.model import Document, Section
from ai_docs_kit.render.components import all_manifests
from ai_docs_kit.source.serialiser import serialise
from ai_docs_kit.testing.golden import compare_facts
from ai_docs_kit.theme import neutral_theme

ROOT = Path(__file__).resolve().parents[1]
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

LIST_ITEMS = [
    (
        "**January** Survey the site. [S1 p.2]\n  - Record the access route.\n  - Check the gate.",
        ["January", "Survey the site.", "Record the access route.", "Check the gate."],
    ),
    ("Confirm the delivery date. [S2 00:41]", ["Confirm the delivery date."]),
    (
        "**March** Publish the findings. [S1 p.4]\n  - Include the site sketch.",
        ["March", "Publish the findings.", "Include the site sketch."],
    ),
]
FIGURES = [("42%", "Completion rate"), ("120", "Sites surveyed"), ("85%", "Return rate"), ("24", "Reports issued")]


def _section(ident, intent, title, body, outline="content"):
    return f'::: {{#{ident} .section intent="{intent}" section="{outline}"}}\n## {title}\n\n{body}\n:::\n'


def _report(*sections):
    return (
        "---\ndoctype: report\nformat: doc\ntitle: Site review\n---\n\n"
        "## Sources\n\n- [S1] Synthetic site register\n- [S2] Synthetic planning transcript\n\n"
        + _section("intro", "body", "Scope", "This report covers the site review.", "introduction")
        + "\n".join(sections)
        + _section("close", "callout", "Findings", "- The review is complete.", "findings")
    )


def _list(order):
    return _section("dates", "bullets", "Review dates", "\n".join("- " + LIST_ITEMS[i][0] for i in order))


def _figures(count):
    return _section(
        "figures",
        "key-numbers",
        "Key figures",
        "\n".join(f"- **{value}** {label} [S1 p.5]" for value, label in FIGURES[:count]),
    )


def _run(args, capsys):
    code = main(args)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _build(tmp_path, text, capsys):
    source = tmp_path / "report.md"
    source.write_text(text, encoding="utf-8")
    code, out, err = _run(["build", str(source)], capsys)
    assert code == 0, f"A document build must accept these intents:\n{out}\n{err}"
    version = Path(out.strip().splitlines()[-1])
    assert (version / "report.pdf").is_file(), out
    assert (version / "report.docx").is_file(), out
    facts = json.loads((version / "layout.json").read_text(encoding="utf-8"))
    page = neutral_theme().tokens.pages["doc"]
    assert facts["pages"]
    for actual in facts["pages"]:
        assert actual["width"] == pytest.approx(page.width, abs=0.1)
        assert actual["height"] == pytest.approx(page.height, abs=0.1)
    return version, facts


def _words(facts, ident):
    return [word for word in facts["words"] if word["section_id"] == ident]


def _assert_in_document_frame(words):
    page = neutral_theme().tokens.pages["doc"]
    assert words
    for word in words:
        box = word["box"]
        assert box["x0"] >= page.margin.left - 0.5, word
        assert box["x1"] <= page.width - page.margin.right + 0.5, word
        assert box["y0"] >= page.margin.top - 0.5, word
        assert box["y1"] <= page.height - page.margin.bottom + 0.5, word


def _assert_rendered_pages(version, ident):
    index = json.loads((version / "pages" / "pages.json").read_text(encoding="utf-8"))
    assert index["sections"].get(ident), f"No rendered page indexed for {ident}"
    for number in index["sections"][ident]:
        image = version / "pages" / f"p{number:02d}.png"
        assert image.is_file() and image.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def _bookmark_paragraphs(path):
    """Read list paragraphs with their enclosing bookmarks from the actual Word copy."""
    with ZipFile(path) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    active = {}
    paragraphs = []
    for event, node in etree.iterwalk(root, events=("start", "end")):
        if event == "start" and node.tag == f"{{{W}}}bookmarkStart":
            active[node.get(f"{{{W}}}id")] = node.get(f"{{{W}}}name")
        elif event == "start" and node.tag == f"{{{W}}}p":
            paragraphs.append({"bookmarks": set(active.values()), "text": "", "node": node})
        elif event == "start" and node.tag == f"{{{W}}}t":
            paragraphs[-1]["text"] += node.text or ""
            paragraphs[-1]["bookmarks"].update(active.values())
        elif event == "start" and node.tag == f"{{{W}}}bookmarkEnd":
            active.pop(node.get(f"{{{W}}}id"), None)
    return paragraphs


@pytest.mark.parametrize("order", [(0, 1, 2), (1, 2, 0)], ids=["headed-first", "plain-first"])
def test_doc_bullets_draw_all_item_fields_and_write_bookmarked_word_list(tmp_path, capsys, order):
    version, facts = _build(tmp_path, _report(_list(order)), capsys)
    words = _words(facts, "dates")
    _assert_in_document_frame(words)
    text = " ".join(word["text"] for word in words)
    expected = [part for index in order for part in LIST_ITEMS[index][1]]
    positions = []
    for part in ["Review dates", *expected]:
        assert part in text, f"The PDF lost {part!r}: {text}"
        positions.append(text.index(part))
    assert positions == sorted(positions), text
    for citation in ("[S1 p.2]", "[S1 p.4]", "[S2 00:41]"):
        assert citation in text, f"The PDF lost the citation {citation!r}: {text}"
    body_sizes = [word["size"] for word in words if word["text"] in ("Survey", "Confirm", "Publish")]
    assert body_sizes == pytest.approx([neutral_theme().tokens.type.scale["doc"].roles["body"].size] * 3)

    path = version / "report.docx"
    paragraphs = _bookmark_paragraphs(path)
    section = [p for p in paragraphs if "dates" in p["bookmarks"]]
    assert section and section[0]["text"] == "Review dates"
    copy_text = " ".join(p["text"] for p in section)
    assert all(part in copy_text for part in expected), copy_text
    assert [copy_text.index(part) for part in expected] == sorted(copy_text.index(part) for part in expected)
    styles = {p.text: p.style.name for p in WordDocument(str(path)).paragraphs}
    for index in order:
        item = LIST_ITEMS[index][1]
        parent = next((p for p in section if item[1 if len(item) > 1 else 0] in p["text"]), None)
        assert parent is not None
        assert styles[parent["text"]].startswith("List") or parent["node"].find(f"{{{W}}}pPr/{{{W}}}numPr") is not None
    for part in expected:
        assert not any(part in p["text"] for p in paragraphs if "dates" not in p["bookmarks"])
    _assert_rendered_pages(version, "dates")


@pytest.mark.parametrize("count", [2, 3, 4])
def test_doc_key_figures_draw_each_value_with_its_label_in_document_style(tmp_path, capsys, count):
    version, facts = _build(tmp_path, _report(_figures(count)), capsys)
    words = _words(facts, "figures")
    _assert_in_document_frame(words)
    assert "Key figures" in " ".join(word["text"] for word in words)
    label_sizes = {
        role.size
        for name, role in neutral_theme().tokens.type.scale["doc"].roles.items()
        if name in ("body", "caption", "label")
    }
    values = []
    for value, label in FIGURES[:count]:
        rendered = [word for word in words if word["text"] == value]
        assert len(rendered) == 1, f"Expected one visible {value!r}"
        values.append(rendered[0])
        matches = [
            words[i : i + len(label.split())]
            for i in range(len(words))
            if [word["text"] for word in words[i : i + len(label.split())]] == label.split()
        ]
        assert len(matches) == 1, f"Expected one visible label {label!r}"
        label_words = matches[0]
        assert all(any(abs(word["size"] - size) < 0.1 for size in label_sizes) for word in label_words)
        assert rendered[0]["size"] > max(word["size"] for word in label_words), "Figures should stand out from labels"
        assert all(word["box"]["page"] == rendered[0]["box"]["page"] for word in label_words)
    assert len({word["box"]["page"] for word in values}) == 1, "A short key-figures section belongs together"
    _assert_rendered_pages(version, "figures")


@pytest.mark.parametrize("intent", ["bullets", "key-numbers"])
def test_new_doc_components_have_buildable_fixtures_and_script_generated_goldens(tmp_path, capsys, intent):
    manifests = [m for m in all_manifests().values() if m.format == "doc" and intent in m.intents]
    assert manifests, f"No document component manifest supports {intent!r}"
    for manifest in manifests:
        assert manifest.fixture, f"{manifest.name} must declare its component fixture"
        fixture = ROOT / manifest.fixture
        golden = fixture.with_suffix(".facts.json")
        assert fixture.is_file(), f"Missing component fixture: {fixture}"
        assert golden.is_file(), f"Generate {golden} with scripts/golden_facts.py"
        data = yaml.safe_load(fixture.read_text(encoding="utf-8"))
        assert data["intent"] == intent
        section = Section.model_validate(data)
        assert section.id, f"{fixture} must give the section a stable id"
        work = tmp_path / manifest.name
        work.mkdir()
        doc = Document(front={"doctype": "report"}, format="doc", sections=[section])
        version, _ = _build(work, serialise(doc), capsys)
        composition = json.loads((version / "composition.json").read_text(encoding="utf-8"))
        assert composition["sections"][0]["component"] == manifest.name
        _assert_rendered_pages(version, section.id)

        generated = work / "goldens"
        generated.mkdir()
        shutil.copyfile(fixture, generated / fixture.name)
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "golden_facts.py"), fixture.stem, "--fixtures", str(generated)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        expected = json.loads(golden.read_text(encoding="utf-8"))
        actual = json.loads((generated / golden.name).read_text(encoding="utf-8"))
        assert actual and any(role["words"] for role in actual.values()), "A golden must capture visible text"
        assert compare_facts(actual, expected) == []


@pytest.mark.parametrize("reverse", [False, True], ids=["list-first", "figures-first"])
def test_doc_outline_check_accepts_lists_and_figures_but_still_refuses_unknown_intents(tmp_path, capsys, reverse):
    sections = [_list((0, 1, 2)), _figures(2)]
    if reverse:
        sections.reverse()
    source = tmp_path / "report.md"
    text = _report(*sections)
    source.write_text(text, encoding="utf-8")
    for intent in ("bullets", "key-numbers"):
        unknown = tmp_path / f"unknown-{intent}.md"
        control = text.replace(f'intent="{intent}"', 'intent="no-such-intent"')
        # Keep the other section supported so this refusal identifies the unknown intent.
        control = control.replace('intent="bullets"', 'intent="callout"').replace(
            'intent="key-numbers"', 'intent="callout"'
        )
        unknown.write_text(control, encoding="utf-8")
        rejected = tmp_path / f"rejected-{intent}"
        code, out, err = _run(["check", str(unknown), "--outline", "--out", str(rejected)], capsys)
        assert code == 1, (out, err)
        report = json.loads((rejected / f"{unknown.stem}.findings.json").read_text(encoding="utf-8"))
        assert any(f["rule_id"] == "source.intent-known" and f["severity"] == "error" for f in report)
        code, out, err = _run(["build", str(unknown), "--out", str(tmp_path / f"build-{intent}")], capsys)
        assert code == 2 and "no-such-intent" in err, (out, err)
    out_dir = tmp_path / "checked"
    code, out, err = _run(["check", str(source), "--outline", "--out", str(out_dir)], capsys)
    assert code == 0, f"A conforming report must accept both intents:\n{out}\n{err}"
    findings = json.loads((out_dir / "report.findings.json").read_text(encoding="utf-8"))
    assert not any(finding["severity"] == "error" for finding in findings), findings
