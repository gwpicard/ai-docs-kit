"""Issue 372: paragraph list markers survive canonical and CLI saves.

Extend the source round-trip coverage beside the locked attribute-escape tests.
Each regression includes ordinary prose and real list items as passing controls.
"""

from pathlib import Path

import pytest
import yaml

from ai_docs_kit.cli import main
from ai_docs_kit.model import Citation, Item, Section
from ai_docs_kit.source import parse, serialise

CHOOSER = Path(__file__).resolve().parents[1] / "src/ai_docs_kit/render/chooser.yaml"
INTENTS = yaml.safe_load(CHOOSER.read_text(encoding="utf-8"))["intents"]
MARKERS = [
    ("-", r"\-"),
    ("*", r"\*"),
    ("+", r"\+"),
    ("1.", r"1\."),
    ("12)", r"12\)"),
    ("0.", r"0\."),
    ("123)", r"123\)"),
]
PROSE = [
    "Keep - and * and + inside prose, with 1. and 12) inside too.",
    "-joined text, *joined text and +joined text have no marker space.",
    "1.joined text and 12)joined text have no marker space.",
    r"Keep \- and \* and \+ and 1\. and 12\) inside prose.",
    r"\q stays literal.",
    r"\-joined text stays literal.",
    r"1\.joined text stays literal.",
    r"\\- two backslashes stay literal.",
]
ITEMS = "- **Lead** keep - and * and + and 1. and 12) here. [S1 p.4]\n  - keep \\- here.\n- plain item."
FRONT = "---\ndoctype: report\nformat: doc\n---\n\n## Sources\n\n- [S1] A synthetic note.\n\n"


def _block(body, intent="body"):
    return f'::: {{#marker .section intent="{intent}"}}\n{body}\n:::\n'


def _document(paragraphs):
    document, findings = parse(FRONT + _block(ITEMS + "\n\n" + "\n\n".join(PROSE)))
    assert findings == []
    assert document.sections[0].paragraphs == PROSE
    document.sections[0].paragraphs = paragraphs
    return document


@pytest.mark.parametrize(("marker", "escaped"), MARKERS)
@pytest.mark.parametrize("seed_first", [True, False], ids=["seed-first", "seed-last"])
def test_serialiser_escapes_only_a_paragraphs_leading_list_marker(marker, escaped, seed_first):
    sentence = f"{marker} keep this as a paragraph."
    paragraphs = [sentence, *PROSE] if seed_first else [*PROSE, sentence]
    document = _document(paragraphs)
    escaped_paragraphs = [f"{escaped} keep this as a paragraph." if p == sentence else p for p in paragraphs]
    expected = FRONT + _block(ITEMS + "\n\n" + "\n\n".join(escaped_paragraphs))

    text = serialise(document)
    assert text == expected, "Only leading paragraph markers should gain a Markdown escape"
    restored, findings = parse(text)
    assert findings == []
    assert restored == document
    assert serialise(restored) == text


@pytest.mark.parametrize(("marker", "escaped"), MARKERS)
def test_parser_removes_exactly_the_leading_paragraph_marker_escape(marker, escaped):
    # Inline escapes, item bodies, sub-lines and code are not paragraph escapes.
    code = f"{escaped} keep this code literal."
    body = "\n\n".join([ITEMS, *PROSE, f"{escaped} keep this as a paragraph.", f"```\n{code}\n```"])
    document, findings = parse(FRONT + _block(body))
    assert findings == []
    section = document.sections[0]
    assert section.items == [
        Item(
            head="Lead",
            body="keep - and * and + and 1. and 12) here.",
            sub=[r"keep \- here."],
            citations=[Citation(key="S1", locator="p.4")],
        ),
        Item(body="plain item."),
    ]
    assert section.code == [code]
    assert section.paragraphs == [*PROSE, f"{marker} keep this as a paragraph."]


@pytest.mark.parametrize("intent", INTENTS)
@pytest.mark.parametrize("number_first", [True, False], ids=["number-first", "hyphen-first"])
def test_every_chooser_intent_has_equal_sections_and_stable_text_after_saving(intent, number_first):
    format_ = "doc" if "doc" in INTENTS[intent] else "slides"
    # Before any item, indentation lets the existing parser seed a hyphen paragraph.
    # Serialisation removes that indentation and currently turns it into an item.
    seeds = ["  - keep this sentence as prose.", "1. keep this sentence as prose."]
    if number_first:
        seeds.reverse()
    paragraphs = [line.strip() for line in seeds] + PROSE
    attributes = r' because="Use \"quoted\" wording at C:\\notes." redraft="First line.\nSecond line."'
    opening = f'::: {{#marker .section intent="{intent}"{attributes}}}'
    body = "\n\n".join(
        [
            "## Marker report",
            *seeds,
            ITEMS,
            *PROSE,
            "> note: Keep the pace.\n> spoken: Keep the wording.\n> source: A synthetic note.",
        ]
    )
    source = FRONT.replace("format: doc", f"format: {format_}") + f"{opening}\n{body}\n:::\n"
    original, findings = parse(source)
    assert findings == []
    section = original.sections[0]
    assert section.paragraphs == paragraphs
    assert section.because == 'Use "quoted" wording at C:\\notes.'
    assert section.redraft == "First line.\nSecond line."
    assert len(section.items) == 2
    assert section.items[0].sub == [r"keep \- here."]
    assert section.items[0].citations == [Citation(key="S1", locator="p.4")]

    once = serialise(original)
    restored, findings = parse(once)
    assert findings == []
    assert restored.sections == original.sections, "Saving must preserve each Section, including seeded paragraphs"
    assert restored == original
    assert serialise(restored) == once
    assert r"\- keep this sentence as prose." in once
    assert r"1\. keep this sentence as prose." in once


@pytest.mark.parametrize("format_", ["doc", "slides"])
@pytest.mark.parametrize("number_first", [True, False], ids=["number-first", "hyphen-first"])
def test_section_put_get_preserves_escaped_paragraphs_through_repeated_saves(tmp_path, capsys, format_, number_first):
    intent = "body" if format_ == "doc" else "statement"
    header = f"---\ndoctype: report\nformat: {format_}\n---\n\n"
    header += "## Sources\n\n- [S1] keep this sentence as prose. 1. 12)\n\n"
    working = tmp_path / "note.md"
    sibling = Section(id="other", intent=intent, paragraphs=["keep the other section."])
    working.write_text(
        header
        + _block("keep the original paragraph.", intent)
        + f'\n::: {{#other .section intent="{intent}"}}\nkeep the other section.\n:::\n',
        encoding="utf-8",
    )
    seeds = [r"\- keep this sentence as prose.", r"1\. keep this sentence as prose."]
    if number_first:
        seeds.reverse()
    block = _block("\n\n".join(seeds + ["keep - inside prose."]), intent)
    expected_paragraphs = [line.replace("\\", "") for line in seeds] + ["keep - inside prose."]
    replacement = tmp_path / "replacement.md"

    for _ in range(3):
        replacement.write_text(block, encoding="utf-8")
        result = main(["section", "put", str(working), "marker", "--from", str(replacement)])
        output = capsys.readouterr()
        assert result == 0, output.err
        assert main(["section", "get", str(working), "marker"]) == 0
        output = capsys.readouterr()
        returned, separator, _sources = output.out.partition("\n\n## Sources")
        assert separator
        assert returned + "\n" == block
        saved, findings = parse(working.read_text(encoding="utf-8"))
        assert findings == []
        assert saved.sections[1] == sibling
        assert saved.sections[0].items == []
        assert saved.sections[0].paragraphs == expected_paragraphs, "The working model must contain no marker escape"
        block = returned + "\n"
