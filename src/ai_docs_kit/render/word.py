"""The Word copy of a doc build: the text for review, each section inside a bookmark named by its id."""

from pathlib import Path
from typing import Any

from docx import Document as WordDocument
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import RGBColor

from ai_docs_kit.bookmark_names import bookmark_name, is_hashed
from ai_docs_kit.model.source import content_fields
from ai_docs_kit.render.compose import ComposedSection, Composition
from ai_docs_kit.store.stamp import add_docx_properties
from ai_docs_kit.theme import Theme
from ai_docs_kit.xml_text import strip_xml_illegal

LABELS = {
    "chart": "Chart",
    "chart-table": "Chart",
    "table": "Table",
    "full-image": "Figure",
    "image-with-text": "Figure",
}
THEME_ATTRIBUTES = ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme")


def _style(document: Any, name: str, family: str, colour: str) -> None:
    """Give a built-in style the theme's font and colour, dropping the template's own theme references."""
    style = document.styles[name]
    style.font.name = family
    style.font.color.rgb = RGBColor.from_string(colour.lstrip("#").upper())
    fonts = style.element.rPr.find(qn("w:rFonts"))
    for attribute in THEME_ATTRIBUTES:
        fonts.attrib.pop(qn(f"w:{attribute}"), None)
    colour_element = style.element.rPr.find(qn("w:color"))
    for attribute in ("themeColor", "themeShade", "themeTint"):
        colour_element.attrib.pop(qn(f"w:{attribute}"), None)


def _item_text(item: dict[str, Any]) -> str:
    text = f"{item['head'].rstrip(':')}: {item['body']}" if item.get("head") else item["body"]
    return " ".join([text, *item.get("sub", [])])


def _lines(section: ComposedSection, numbers: dict[str, int]) -> list[tuple[str, str]]:
    """The (style, text) lines of one section; a chart, table or figure is one numbered line."""
    label = LABELS.get(section.component)
    props = section.props
    reference = None
    if label:
        numbers[label] = numbers.get(label, 0) + 1
        reference = ("Normal", f"[{label} {numbers[label]}: {props['title']}]")
        if not props.get("content_order"):
            return [reference]
    lines = [("Heading 1", props["title"])] if props["title"] and not label else []
    # Older compositions retain their original paragraphs-first Word order.
    fallback = [
        *[f"paragraphs[{i}]" for i in range(len(props["paragraphs"]))],
        *[f"items[{i}]" for i in range(len(props["items"]))],
    ]
    order = content_fields(
        len(props["paragraphs"]), len(props["items"]), bool(label), props.get("content_order", fallback)
    )
    for field in order:
        if field == "data" and reference:
            lines.append(reference)
        elif field.startswith("paragraphs["):
            lines.append(("Normal", props["paragraphs"][int(field[11:-1])]))
        elif field.startswith("items["):
            lines.append(("List Bullet", _item_text(props["items"][int(field[6:-1])])))
    if props["source_line"] and not label:
        lines.append(("Normal", props["source_line"]))
    return lines


def _bookmark(tag: str, number: int, name: str | None = None) -> Any:
    element = OxmlElement(f"w:{tag}")
    element.set(qn("w:id"), str(number))
    if name is not None:
        element.set(qn("w:name"), name)
    return element


def write_docx(path: Path, *, comp: Composition, theme: Theme) -> Path:
    """Write the review copy to `path`: the sections' text in order, fonts and colours from the theme's tokens."""
    tokens = theme.tokens
    families = {key: family.name for key, family in tokens.type.families.items()}
    scale = tokens.type.scale["doc"].roles
    roles = tokens.colour.roles
    document = WordDocument()
    _style(document, "Normal", families[scale["body"].family], roles["ink"])
    _style(document, "List Bullet", families[scale["body"].family], roles["ink"])
    _style(document, "Heading 1", families[scale["h1"].family], roles["ink"])
    numbers: dict[str, int] = {}
    stored: dict[str, str] = {}
    for number, section in enumerate(comp.sections, 1):
        paragraphs = [
            document.add_paragraph(strip_xml_illegal(text), style=style) for style, text in _lines(section, numbers)
        ]
        if not paragraphs:
            paragraphs = [document.add_paragraph("")]
        name = bookmark_name(section.id)
        if is_hashed(name):
            stored[name] = section.id
        paragraphs[0]._p.insert(1 if paragraphs[0]._p.pPr is not None else 0, _bookmark("bookmarkStart", number, name))
        paragraphs[-1]._p.append(_bookmark("bookmarkEnd", number))
    document.save(str(path))
    if stored:
        add_docx_properties(path, stored)
    return path
