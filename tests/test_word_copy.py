"""The Word copy: text and section bookmarks, one line per chart, theme fonts and colours only.

Each test asserts that the `.docx` exists before it opens it, and imports nothing from
`ai_docs_kit.render.word`, so a missing writer fails by assertion.
"""

import shutil
from pathlib import Path

import pytest
import yaml
from lxml import etree
from tests.support.fixtures import fixture_path

from ai_docs_kit.cli import main

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}

MIXED = """---
doctype: report
format: doc
title: Mixed
---

::: {#intro .section intent="body"}
## Opening

First paragraph of the opening.

Second paragraph of the opening.
:::

::: {#cha01 .section intent="chart"}
## Quarterly results

```data
type: bar
categories: [North, South]
series:
  - name: Current
    values: [4, 6]
```

> source: Company records
:::

::: {#list01 .section intent="callout"}
## Next steps

- Measure the dropped readings.
- Report the count.
:::

::: {#cha02 .section intent="chart"}
## Trend

```data
type: bar
categories: [East, West]
series:
  - name: Current
    values: [7, 9]
```

> source: Internal data
:::
"""

IDS = ["intro", "cha01", "list01", "cha02"]
TOKENS = Path(__file__).resolve().parents[1] / "src" / "ai_docs_kit" / "themes" / "neutral" / "tokens.yaml"
THEME = TOKENS.with_name("theme.yaml")


def _run_build(file: Path, capsys) -> tuple[int, Path | None]:
    try:
        code = main(["build", str(file)])
        lines = capsys.readouterr().out.strip().splitlines()
        return code, Path(lines[-1]) if lines else None
    except BaseException:  # a failed build must show up as a failed assertion, not an error
        return -1, None


@pytest.fixture
def mixed(tmp_path, capsys):
    file = tmp_path / "mixed.md"
    file.write_text(MIXED, encoding="utf-8")
    code, version = _run_build(file, capsys)
    return file, code, version


def _docx(mixed) -> Path:
    file, code, version = mixed
    assert code == 0 and version is not None, "the doc build must succeed"
    path = version / f"{file.stem}.docx"
    assert path.is_file(), f"no Word copy at {path}"
    return path


def _document_xml(path: Path) -> etree._Element:
    import zipfile

    with zipfile.ZipFile(path) as archive:
        return etree.fromstring(archive.read("word/document.xml"))


def _ranges(root: etree._Element) -> dict[str, str]:
    """The text of each bookmark, in document order, paragraphs joined by newlines."""
    open_marks: dict[str, str] = {}
    text: dict[str, list[str]] = {}
    for event, node in etree.iterwalk(root, events=("start", "end")):
        tag = etree.QName(node).localname
        if event == "start" and tag == "bookmarkStart":
            open_marks[node.get(f"{{{W}}}id")] = node.get(f"{{{W}}}name")
            text.setdefault(node.get(f"{{{W}}}name"), [])
        elif event == "start" and tag == "bookmarkEnd":
            open_marks.pop(node.get(f"{{{W}}}id"), None)
        elif event == "start" and tag == "t":
            for name in open_marks.values():
                text[name].append(node.text or "")
        elif event == "end" and tag == "p":
            for name in open_marks.values():
                text[name].append("\n")
    return {name: "".join(parts) for name, parts in text.items()}


def _paragraphs(path: Path) -> list[str]:
    from docx import Document

    return [p.text for p in Document(str(path)).paragraphs if p.text.strip()]


def test_a_doc_build_writes_the_docx_beside_the_pdf_and_into_the_version(mixed):
    file, code, version = mixed
    copy = _docx(mixed)
    beside_pdf = file.parent / "build" / f"{file.stem}.docx"
    assert beside_pdf.is_file(), f"no Word copy at {beside_pdf}"
    assert beside_pdf.read_bytes() == copy.read_bytes()


def test_headings_and_paragraphs_come_out_in_section_order(mixed):
    lines = _paragraphs(_docx(mixed))
    expected = ["Opening", "First paragraph of the opening.", "Second paragraph of the opening.", "Next steps"]
    positions = [lines.index(text) if text in lines else -1 for text in expected]
    assert -1 not in positions, f"missing text in {lines}"
    assert positions == sorted(positions)
    assert lines.index("Next steps") < lines.index("[Chart 2: Trend]")


def test_each_section_sits_inside_a_bookmark_named_by_its_id(mixed):
    ranges = _ranges(_document_xml(_docx(mixed)))
    assert [name for name in ranges if name in IDS] == IDS
    assert "Opening" in ranges["intro"]
    assert "First paragraph of the opening." in ranges["intro"]
    assert "Second paragraph of the opening." in ranges["intro"]
    assert "Next steps" not in ranges["intro"]
    assert "Opening" not in ranges["list01"]


def test_list_items_sit_inside_their_sections_bookmark(mixed):
    ranges = _ranges(_document_xml(_docx(mixed)))
    assert "Measure the dropped readings." in ranges.get("list01", "")
    assert "Report the count." in ranges.get("list01", "")
    assert "Measure the dropped readings." not in ranges.get("intro", "")


def test_a_chart_becomes_one_numbered_line_inside_its_bookmark(mixed):
    path = _docx(mixed)
    lines = _paragraphs(path)
    assert lines.count("[Chart 1: Quarterly results]") == 1
    assert lines.count("[Chart 2: Trend]") == 1
    ranges = _ranges(_document_xml(path))
    assert ranges.get("cha01", "").strip() == "[Chart 1: Quarterly results]"
    assert ranges.get("cha02", "").strip() == "[Chart 2: Trend]"
    assert not any(word in "\n".join(lines) for word in ("North", "Company records"))


def _font_of(paragraph, attribute: str):
    """The effective value of a run property: the first run's own, else the style chain's."""
    run = paragraph.runs[0] if paragraph.runs else None
    value = getattr(run.font, attribute, None) if run is not None else None
    if attribute == "color" and value is not None:
        value = value.rgb
    style = paragraph.style
    while value is None and style is not None:
        value = getattr(style.font, attribute)
        if attribute == "color" and value is not None:
            value = value.rgb
        style = style.base_style
    return str(value) if value is not None else None


def _paragraph(path: Path, text: str):
    from docx import Document

    found = [p for p in Document(str(path)).paragraphs if p.text == text]
    assert found, f"no paragraph reading {text!r}"
    return found[0]


def test_heading_and_body_fonts_come_from_the_theme_families(mixed):
    families = yaml.safe_load(THEME.read_text())["type"]["families"]
    path = _docx(mixed)
    assert _font_of(_paragraph(path, "Opening"), "name") == families["display"]["name"]
    assert _font_of(_paragraph(path, "First paragraph of the opening."), "name") == families["text"]["name"]


def test_text_colours_come_from_the_theme_roles(mixed):
    roles = yaml.safe_load(THEME.read_text())["colour"]["roles"]
    allowed = {value.lstrip("#").upper() for value in roles.values()}
    path = _docx(mixed)
    colours = {
        text: (_font_of(_paragraph(path, text), "color") or "").upper()
        for text in ("Opening", "First paragraph of the opening.")
    }
    assert all(colours.values()), f"unset colours: {colours}"
    assert set(colours.values()) <= allowed
    assert colours["First paragraph of the opening."] == roles["ink"].lstrip("#").upper()


def test_nothing_else_is_styled(mixed):
    root = _document_xml(_docx(mixed))
    extras = ("b", "i", "u", "strike", "highlight", "shd", "vertAlign", "caps", "smallCaps")
    found = {
        etree.QName(node).localname
        for rpr in root.iterfind(".//w:r/w:rPr", NS)
        for node in rpr
        if etree.QName(node).localname in extras
    }
    assert not found, f"run formatting beyond fonts and colours: {sorted(found)}"
    assert not root.findall(".//w:tbl", NS), "a chart is one line, not a table"
    assert not root.findall(".//w:drawing", NS), "a chart is one line, not a picture"


def test_only_a_doc_build_writes_a_docx_and_no_pptx(mixed, tmp_path, capsys):
    path = _docx(mixed)
    file, _, version = mixed
    assert not list(file.parent.rglob("*.pptx")), "a doc build wrote a .pptx"
    assert path.name == "mixed.docx"
    deck = tmp_path / "deck" / "deck.md"
    deck.parent.mkdir()
    shutil.copyfile(fixture_path("slides", "deck.md"), deck)
    code, _ = _run_build(deck, capsys)
    assert code == 0
    assert not list(deck.parent.rglob("*.docx")), "a slides build wrote a .docx"
