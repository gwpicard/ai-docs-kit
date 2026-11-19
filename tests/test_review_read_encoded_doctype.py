"""The refusal of entity declarations must also cover non-UTF-8 Office parts."""

import zipfile
from pathlib import Path

import pytest

from ai_docs_kit.review.pptx_read import read_deck
from ai_docs_kit.review.word_read import read_word

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"


@pytest.mark.parametrize("kind", ["docx", "pptx"])
@pytest.mark.parametrize("encoding", ["utf-16", "utf-32"])
def test_encoded_entity_declarations_are_refused(tmp_path: Path, kind: str, encoding: str) -> None:
    if kind == "docx":
        part = "word/document.xml"
        root_name = "w:document"
        xml = (
            f'<w:document xmlns:w="{W}"><w:body><w:p>'
            '<w:bookmarkStart w:id="1" w:name="alpha"/>'
            "<w:r><w:t>Before ENTITY_MARKER after</w:t></w:r>"
            '<w:bookmarkEnd w:id="1"/></w:p></w:body></w:document>'
        )
        extra = {}
        reader = read_word
    else:
        part = "ppt/slides/slide1.xml"
        root_name = "p:sld"
        xml = (
            f'<p:sld xmlns:p="{P}" xmlns:a="{A}"><p:cSld><p:spTree><p:sp>'
            '<p:nvSpPr><p:cNvPr id="2" name="alpha/title"/></p:nvSpPr>'
            "<p:txBody><a:p><a:r><a:t>Before ENTITY_MARKER after</a:t></a:r></a:p></p:txBody>"
            "</p:sp></p:spTree></p:cSld></p:sld>"
        )
        extra = {
            "ppt/presentation.xml": (
                f'<p:presentation xmlns:p="{P}" xmlns:r="{R}">'
                '<p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst></p:presentation>'
            ).encode(),
            "ppt/_rels/presentation.xml.rels": (
                f'<Relationships xmlns="{PKG}"><Relationship Id="rId1" '
                f'Type="{R}/slide" Target="slides/slide1.xml"/></Relationships>'
            ).encode(),
        }
        reader = read_deck
    copy = tmp_path / f"copy.{kind}"
    declaration = f'<?xml version="1.0" encoding="{encoding.upper()}"?>'
    with zipfile.ZipFile(copy, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in extra.items():
            archive.writestr(name, data)
        archive.writestr(part, (declaration + xml).encode(encoding))
    assert reader(copy).order == ["alpha"]  # The encoding itself is supported.
    hostile = (
        declaration
        + f'<!DOCTYPE {root_name} [<!ENTITY edit "Revised wording">]>'
        + xml.replace("ENTITY_MARKER", "&edit;")
    )
    with zipfile.ZipFile(copy, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in extra.items():
            archive.writestr(name, data)
        archive.writestr(part, hostile.encode(encoding))
    refused = False
    try:
        result = reader(copy)
    except ValueError:
        refused = True
    assert refused, f"The reader accepted a {encoding} entity declaration and returned {result!r}"
