"""Record a version number in an Office copy's custom document properties."""

from pathlib import Path
from typing import Any

from docx.opc.packuri import PackURI
from lxml import etree  # type: ignore[import-untyped]

PROPERTY = "ai-docs-kit-version"
PART_NAME = "/docProps/custom.xml"
CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.custom-properties+xml"
RELATIONSHIP = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties"
_NS = "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
_VT = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"
_FMTID = "{D5CDD505-2E9C-101B-9397-08002B2CF9AE}"


def _blob(number: int) -> bytes:
    root = etree.Element(f"{{{_NS}}}Properties", nsmap={None: _NS, "vt": _VT})
    prop = etree.SubElement(root, f"{{{_NS}}}property", fmtid=_FMTID, pid="2", name=PROPERTY)
    etree.SubElement(prop, f"{{{_VT}}}lpwstr").text = str(number)
    return bytes(etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True))


def _add(package: Any, make: Any, number: int) -> None:
    rels = package.rels if hasattr(package, "rels") else package._rels
    for rel in list(rels.values()):
        if rel.reltype == RELATIONSHIP:
            rels.pop(rel.rId)
    part = make(PackURI(PART_NAME), CONTENT_TYPE, _blob(number), package)
    package.relate_to(part, RELATIONSHIP)


def stamp_docx(path: Path, number: int) -> None:
    from docx import Document
    from docx.opc.part import Part

    document = Document(str(path))
    _add(document.part.package, Part, number)
    document.save(str(path))


def stamp_pptx(path: Path, number: int) -> None:
    from pptx import Presentation
    from pptx.opc.package import Part

    deck = Presentation(str(path))
    _add(deck.part.package, lambda name, ctype, blob, package: Part(name, ctype, package, blob), number)
    deck.save(str(path))


def stamp(path: Path, number: int) -> None:
    (stamp_pptx if path.suffix.lower() == ".pptx" else stamp_docx)(path, number)


def read_version_property(path: Path) -> int | None:
    """The version number a copy records, or None when it has none or the value is not a number."""
    import zipfile

    try:
        with zipfile.ZipFile(path) as archive:
            root = etree.fromstring(archive.read(PART_NAME.lstrip("/")))
    except (KeyError, OSError, zipfile.BadZipFile, etree.XMLSyntaxError):
        return None
    for node in root:
        if node.get("name") == PROPERTY:
            text = "".join(node.itertext()).strip()
            return int(text) if text.isdigit() else None
    return None
