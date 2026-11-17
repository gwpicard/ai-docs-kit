"""The Word copy of a doc build: the text for review, each section inside a bookmark named by its id."""

from pathlib import Path
from typing import Any

from docx import Document as WordDocument
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import RGBColor

from ai_docs_kit.render.compose import ComposedSection, Composition
from ai_docs_kit.theme import Theme

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
    style.font.color.rgb = RGBColor.from_string(colour.lstrip("#").upper())  # type: ignore[no-untyped-call]
    fonts = style.element.rPr.find(qn("w:rFonts"))
    for attribute in THEME_ATTRIBUTES:
        fonts.attrib.pop(qn(f"w:{attribute}"), None)
    colour_element = style.element.rPr.find(qn("w:color"))
    for attribute in ("themeColor", "themeShade", "themeTint"):
        colour_element.attrib.pop(qn(f"w:{attribute}"), None)


def _item_text(item: dict[str, Any]) -> str:
    text = f"{item['head']}: {item['body']}" if item.get("head") else item["body"]
    return " ".join([text, *item.get("sub", [])])


def _lines(section: ComposedSection, numbers: dict[str, int]) -> list[tuple[str, str]]:
    """The (style, text) lines of one section; a chart, table or figure is one numbered line."""
    label = LABELS.get(section.component)
    if label:
        numbers[label] = numbers.get(label, 0) + 1
        return [("Normal", f"[{label} {numbers[label]}: {section.props['title']}]")]
    props = section.props
    lines = [("Heading 1", props["title"])] if props["title"] else []
    lines += [("Normal", text) for text in props["paragraphs"]]
    lines += [("List Bullet", _item_text(item)) for item in props["items"]]
    if props["source_line"]:
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
    for number, section in enumerate(comp.sections, 1):
        paragraphs = [document.add_paragraph(text, style=style) for style, text in _lines(section, numbers)]
        if not paragraphs:
            paragraphs = [document.add_paragraph("")]
        paragraphs[0]._p.insert(
            1 if paragraphs[0]._p.pPr is not None else 0, _bookmark("bookmarkStart", number, section.id)
        )
        paragraphs[-1]._p.append(_bookmark("bookmarkEnd", number))
    document.save(str(path))
    return path
