"""Record a version number in an Office copy's custom document properties."""

import zlib
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


def _blob(properties: dict[str, str], existing: bytes | None = None) -> bytes:
    """The custom properties part: what `existing` holds, with `properties` added or replaced."""
    root = (
        etree.fromstring(existing) if existing else etree.Element(f"{{{_NS}}}Properties", nsmap={None: _NS, "vt": _VT})
    )
    nodes = {node.get("name"): node for node in root}
    pid = max((int(n.get("pid") or 1) for n in root), default=1)
    for name, value in properties.items():
        node = nodes.get(name)
        if node is None:
            pid += 1
            node = etree.SubElement(root, f"{{{_NS}}}property", fmtid=_FMTID, pid=str(pid), name=name)
        for child in list(node):
            node.remove(child)
        etree.SubElement(node, f"{{{_VT}}}lpwstr").text = value
    return bytes(etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True))


def _add(package: Any, make: Any, properties: dict[str, str]) -> None:
    rels = package.rels if hasattr(package, "rels") else package._rels
    existing = None
    for rel in list(rels.values()):
        if rel.reltype == RELATIONSHIP:
            if not rel.is_external:
                existing = rel.target_part.blob
            rels.pop(rel.rId)
    part = make(PackURI(PART_NAME), CONTENT_TYPE, _blob(properties, existing), package)
    package.relate_to(part, RELATIONSHIP)


def add_docx_properties(path: Path, properties: dict[str, str]) -> None:
    """Add custom document properties to a Word copy, keeping the ones it has."""
    from docx import Document
    from docx.opc.part import Part

    document = Document(str(path))
    _add(document.part.package, Part, properties)
    document.save(str(path))


def stamp_docx(path: Path, number: int) -> None:
    add_docx_properties(path, {PROPERTY: str(number)})


def stamp_pptx(path: Path, number: int) -> None:
    from pptx import Presentation
    from pptx.opc.package import Part

    deck = Presentation(str(path))
    _add(
        deck.part.package, lambda name, ctype, blob, package: Part(name, ctype, package, blob), {PROPERTY: str(number)}
    )
    deck.save(str(path))


def stamp(path: Path, number: int) -> None:
    (stamp_pptx if path.suffix.lower() == ".pptx" else stamp_docx)(path, number)


def read_custom_properties(path: Path) -> dict[str, str]:
    """The custom document properties a copy records; empty when it has none or the part cannot be read."""
    import zipfile

    try:
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo(PART_NAME.lstrip("/"))
            if info.file_size > 1 << 20:
                return {}
            data = archive.read(info)
        if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
            return {}
        root = etree.fromstring(data, etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False))
    except (
        KeyError,
        OSError,
        zipfile.BadZipFile,
        etree.XMLSyntaxError,
        ValueError,
        RuntimeError,
        zlib.error,
        EOFError,
    ):
        return {}
    return {n.get("name"): "".join(n.itertext()).strip() for n in root if isinstance(n.tag, str) and n.get("name")}


def read_version_property(path: Path) -> int | None:
    """The version number a copy records, or None when it has none or the value is not a number."""
    text = read_custom_properties(path).get(PROPERTY, "")
    return int(text) if text.isascii() and text.isdigit() else None
