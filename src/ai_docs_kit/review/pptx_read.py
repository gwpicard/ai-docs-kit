"""Read a PowerPoint file into per-field text, comments and emphasis; the archive is treated as hostile."""

import posixpath
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree  # type: ignore[import-untyped]

from ai_docs_kit.review.word_read import ARCHIVE_ERRORS, Comment, _parse, _part, check_archive

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
P188 = "http://schemas.microsoft.com/office/powerpoint/2018/8/main"
AC = "http://schemas.microsoft.com/office/drawing/2013/main/command"
# Field paths contain no slash, so the final slash separates them from section ids.
NAME = re.compile(r"(\S+)/(\S.*)")

Hint = tuple[str, str, str | None]


@dataclass
class DeckComment(Comment):
    slide: int = 0
    shape: str | None = None
    id: str | None = None
    reply_to: str | None = None


@dataclass
class DeckText:
    order: list[str] = field(default_factory=list)
    slide_of: dict[str, int] = field(default_factory=dict)
    fields: dict[str, dict[str, str]] = field(default_factory=dict)
    formats: dict[tuple[str, str], list[Hint]] = field(default_factory=dict)
    comments: list[tuple[str | None, DeckComment]] = field(default_factory=list)
    unplaced: list[tuple[str | None, str]] = field(default_factory=list)


def _q(namespace: str, tag: str) -> str:
    return f"{{{namespace}}}{tag}"


def _relationships(archive: zipfile.ZipFile, part: str, label: str) -> list[tuple[str, str, str]]:
    """(id, type, resolved part name) for each internal relationship of `part`."""
    folder, _, base = part.rpartition("/")
    name = f"{folder}/_rels/{base}.rels"
    data = _part(archive, name, label, required=False, kind="PowerPoint")
    if data is None:
        return []
    found = []
    for rel in _parse(data, label, name):
        if rel.get("TargetMode") == "External":
            continue
        target = rel.get("Target") or ""
        resolved = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(folder, target))
        found.append((rel.get("Id") or "", rel.get("Type") or "", resolved))
    return found


def _tree(archive: zipfile.ZipFile, name: str, label: str) -> etree._Element | None:
    data = _part(archive, name, label, required=False, kind="PowerPoint")
    return _parse(data, label, name) if data is not None else None


def _paragraphs(body: etree._Element) -> list[str]:
    lines = []
    for paragraph in body.iter(_q(A, "p")):
        parts = []
        for node in paragraph.iter(_q(A, "t"), _q(A, "br")):
            parts.append("\n" if node.tag == _q(A, "br") else node.text or "")
        lines.append("".join(parts))
    return lines


def _runs(body: etree._Element) -> list[Hint]:
    hints: list[Hint] = []
    for run in body.iter(_q(A, "r")):
        text = "".join(t.text or "" for t in run.iter(_q(A, "t")))
        props = run.find(_q(A, "rPr"))
        if props is None or not text.strip():
            continue
        for attribute, kind in (("b", "bold"), ("i", "italic")):
            if props.get(attribute) in ("1", "true"):
                hints.append((kind, text, None))
        colour = props.find(f"{_q(A, 'solidFill')}/{_q(A, 'srgbClr')}")
        if colour is not None and colour.get("val"):
            hints.append(("colour", text, colour.get("val", "").upper()))
    return hints


def _boxes(slide: etree._Element) -> list[tuple[str, str, list[str], list[Hint]]]:
    """The id, name, text lines and run formats of each shape with a text body."""
    found = []
    for shape in slide.iter(_q(P, "sp")):
        props = shape.find(f"{_q(P, 'nvSpPr')}/{_q(P, 'cNvPr')}")
        body = shape.find(_q(P, "txBody"))
        if props is None or body is None:
            continue
        found.append((props.get("id") or "", props.get("name") or "", _paragraphs(body), _runs(body)))
    return found


def _legacy(archive: zipfile.ZipFile, label: str, part: str, authors: dict[str, str], number: int) -> list[DeckComment]:
    root = _tree(archive, part, label)
    found = []
    for node in root.iter(_q(P, "cm")) if root is not None else []:
        text = node.find(_q(P, "text"))
        who = authors.get(node.get("authorId") or "")
        found.append(DeckComment(who, ("".join(text.itertext()) if text is not None else "").strip(), [], slide=number))
    return found


def _modern(
    archive: zipfile.ZipFile, label: str, part: str, authors: dict[str, str], number: int, names: dict[str, str]
) -> list[DeckComment]:
    root = _tree(archive, part, label)
    found = []
    for node in root.iter(_q(P188, "cm")) if root is not None else []:
        body = node.find(_q(P188, "txBody"))
        text = "\n".join(_paragraphs(body)) if body is not None else ""
        marker = node.find(f".//{_q(AC, 'spMk')}")
        shape = names.get(marker.get("id") or "") if marker is not None else None
        who = authors.get(node.get("authorId") or "")
        identifier = node.get("id")
        anchor = [shape] if shape else []
        found.append(DeckComment(who, text.strip(), anchor, slide=number, shape=shape, id=identifier))
        for reply in node.iterfind(f"{_q(P188, 'replyLst')}/{_q(P188, 'reply')}"):
            reply_body = reply.find(_q(P188, "txBody"))
            reply_text = "\n".join(_paragraphs(reply_body)) if reply_body is not None else ""
            reply_who = authors.get(reply.get("authorId") or "")
            found.append(
                DeckComment(
                    reply_who,
                    reply_text.strip(),
                    anchor,
                    slide=number,
                    shape=shape,
                    id=reply.get("id"),
                    reply_to=identifier,
                )
            )
    return found


def _authors(
    archive: zipfile.ZipFile, label: str, rels: list[tuple[str, str, str]]
) -> tuple[dict[str, str], dict[str, str]]:
    legacy: dict[str, str] = {}
    modern: dict[str, str] = {}
    named = {kind.rsplit("/", 1)[-1]: part for _, kind, part in rels}
    root = _tree(archive, named.get("commentAuthors", "ppt/commentAuthors.xml"), label)
    for node in root.iter(_q(P, "cmAuthor")) if root is not None else []:
        legacy[node.get("id") or ""] = node.get("name") or ""
    root = _tree(archive, named.get("authors", "ppt/authors.xml"), label)
    for node in root.iter(_q(P188, "author")) if root is not None else []:
        modern[node.get("id") or ""] = node.get("name") or ""
    return legacy, modern


def read_deck(path: Path, sections: set[str] | None = None) -> DeckText:
    """The text of each named text box, by section, in slide order, with the comments of both formats.

    `sections` names the section ids that count as sections; None counts every name of the form `<id>/<path>`.
    """
    label = path.name
    result = DeckText()
    try:
        with zipfile.ZipFile(path) as archive:
            check_archive(archive, label)
            _read(archive, label, sections, result)
    except ARCHIVE_ERRORS as error:
        raise ValueError(f"{label}: not a readable PowerPoint file ({error})") from None
    return result


def _read(archive: zipfile.ZipFile, label: str, sections: set[str] | None, result: DeckText) -> None:
    presentation = _part(archive, "ppt/presentation.xml", label, required=True, kind="PowerPoint")
    assert presentation is not None
    rels = _relationships(archive, "ppt/presentation.xml", label)
    targets = {rid: part for rid, _, part in rels}
    legacy_authors, modern_authors = _authors(archive, label, rels)
    root = _parse(presentation, label, "ppt/presentation.xml")
    last: str | None = None
    for position, entry in enumerate(root.iter(_q(P, "sldId")), start=1):
        part = targets.get(entry.get(_q(R, "id")) or "")
        slide = _tree(archive, part, label) if part else None
        if part is None or slide is None:
            continue
        boxes = _boxes(slide)
        names = {shape_id: name for shape_id, name, _, _ in boxes}
        owner: str | None = None
        for _, name, _, _ in boxes:
            match = NAME.fullmatch(name)
            if match and (sections is None or match.group(1) in sections):
                owner = owner or match.group(1)
        if owner in result.slide_of:
            owner = None  # a second slide for a section counts as new text, not as the section
        elif owner is not None:
            result.order.append(owner)
            result.slide_of[owner] = position
        for _, name, lines, hints in boxes:
            match = NAME.fullmatch(name)
            text = "\n".join(lines).strip()
            if match and owner is not None and match.group(1) == owner:
                path = match.group(2)
                fields = result.fields.setdefault(owner, {})
                if path in fields:
                    # Duplicated boxes keep their name but cannot replace the first box's wording.
                    if text:
                        result.unplaced.append((owner, text))
                else:
                    fields[path] = text
                    result.formats[(owner, path)] = hints
            elif text:
                result.unplaced.append((last, text))
        # Native tables hold DrawingML paragraphs outside the ordinary text shapes.
        for table in slide.iter(_q(A, "tbl")):
            text = "\n".join(_paragraphs(table)).strip()
            if text:
                result.unplaced.append((last, text))
        if owner is not None:
            last = owner
        for _, kind, target in _relationships(archive, part, label):
            suffix = kind.rsplit("/", 1)[-1]
            if suffix == "comments" and kind.startswith(R):
                found = _legacy(archive, label, target, legacy_authors, position)
            elif suffix == "comments":
                found = _modern(archive, label, target, modern_authors, position, names)
            else:
                continue
            result.comments.extend((owner, comment) for comment in found)
