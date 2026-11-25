"""Read a Word file into per-section text, comments and emphasis; the archive is treated as hostile."""

import lzma
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree  # type: ignore[import-untyped]

from ai_docs_kit.bookmark_names import is_hashed, section_of
from ai_docs_kit.store.stamp import read_custom_properties

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MAX_ENTRIES = 2000
MAX_PART = 32 << 20
MAX_TOTAL = 128 << 20
SKIPPED = {"del", "moveFrom", "delText", "instrText"}
PARSER_OPTIONS = {"resolve_entities": False, "no_network": True, "load_dtd": False, "huge_tree": False}


def _q(tag: str) -> str:
    return f"{{{W}}}{tag}"


@dataclass
class Comment:
    author: str | None
    text: str
    anchor: list[str] = field(default_factory=list)
    spans: list[str] = field(default_factory=list)


@dataclass
class WordText:
    order: list[str] = field(default_factory=list)
    titles: dict[str, str] = field(default_factory=dict)
    paragraphs: dict[str, list[str]] = field(default_factory=dict)
    items: dict[str, list[str]] = field(default_factory=dict)
    emphasis: dict[str, list[tuple[str, str, str | None]]] = field(default_factory=dict)
    comments: list[tuple[str | None, Comment]] = field(default_factory=list)
    unplaced: list[tuple[str | None, str]] = field(default_factory=list)
    tracked: bool = False


def _is_list_item(node: etree._Element) -> bool:
    props = node.find(_q("pPr"))
    if props is None:
        return False
    style = props.find(_q("pStyle"))
    name = (style.get(_q("val")) or "") if style is not None else ""
    return name.startswith("List") or props.find(_q("numPr")) is not None


def _is_heading(node: etree._Element) -> bool:
    style = node.find(f"{_q('pPr')}/{_q('pStyle')}")
    return style is not None and (style.get(_q("val")) or "").startswith("Heading")


def _part(archive: zipfile.ZipFile, name: str, label: str, *, required: bool, kind: str = "Word") -> bytes | None:
    try:
        info = archive.getinfo(name)
    except KeyError:
        if required:
            raise ValueError(f"{label}: not a {kind} file (no {name})") from None
        return None
    if info.file_size > MAX_PART:
        raise ValueError(f"{label}: {name} is too large to read safely")
    with archive.open(info) as handle:
        data = handle.read(MAX_PART + 1)
    if len(data) > MAX_PART:
        raise ValueError(f"{label}: {name} is too large to read safely")
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise ValueError(f"{label}: {name} declares entities, which are not read")
    return data


def _parse(data: bytes, label: str, name: str) -> etree._Element:
    try:
        root = etree.fromstring(data, etree.XMLParser(**PARSER_OPTIONS))
    except etree.XMLSyntaxError as error:
        raise ValueError(f"{label}: {name} cannot be read safely: {error}") from None
    # Parser metadata recognises doctypes in every supported XML encoding.
    if root.getroottree().docinfo.doctype:
        raise ValueError(f"{label}: {name} declares entities, which are not read")
    return root


ARCHIVE_ERRORS = (
    zipfile.BadZipFile,
    zipfile.LargeZipFile,
    EOFError,
    NotImplementedError,
    RuntimeError,
    zlib.error,
)


def check_archive(archive: zipfile.ZipFile, label: str) -> None:
    infos = archive.infolist()
    if len(infos) > MAX_ENTRIES:
        raise ValueError(f"{label}: too many entries in the archive ({len(infos)})")
    if sum(i.file_size for i in infos) > MAX_TOTAL:
        raise ValueError(f"{label}: the archive is too large to read safely")


def _open(path: Path) -> tuple[etree._Element, etree._Element | None]:
    label = path.name
    try:
        with zipfile.ZipFile(path) as archive:
            check_archive(archive, label)
            body = _part(archive, "word/document.xml", label, required=True)
            notes = _part(archive, "word/comments.xml", label, required=False)
    except (*ARCHIVE_ERRORS, lzma.LZMAError) as error:
        raise ValueError(f"{label}: not a readable Word file ({error})") from None
    assert body is not None
    return _parse(body, label, "word/document.xml"), (_parse(notes, label, "word/comments.xml") if notes else None)


def _read_comments(root: etree._Element | None) -> dict[str, Comment]:
    found: dict[str, Comment] = {}
    if root is None:
        return found
    for node in root.iter(_q("comment")):
        text = "\n".join("".join(t.text or "" for t in p.iter(_q("t"))) for p in node.iter(_q("p")))
        found[node.get(_q("id")) or ""] = Comment(node.get(_q("author")) or "", text.strip())
    return found


class _Walker:
    def __init__(
        self, sections: set[str] | None, comments: dict[str, Comment], stored: dict[str, str] | None = None
    ) -> None:
        self.known = sections
        self.stored = stored or {}
        self.result = WordText()
        self.comments = comments
        self.open: dict[str, str] = {}
        self.ranges: set[str] = set()
        self.placed: set[str] = set()
        self.touched: list[str] = []
        self.buffer: list[str] = []
        self.hints: list[tuple[str, str, str | None]] = []
        self.last: str | None = None
        self.listing: str | None = None

    def current(self) -> str | None:
        return next(iter(self.open.values()), None)

    def _text(self, text: str) -> None:
        self.buffer.append(text)
        for identifier in self.ranges:
            if identifier in self.comments:
                self.comments[identifier].anchor.append(text)

    def _start(self, name: str) -> None:
        if self.known is not None and name not in self.known:
            return
        if name not in self.result.order:
            self.result.order.append(name)
        if name not in self.touched:
            self.touched.append(name)
        for identifier in self.ranges:
            if identifier in self.comments:
                self._span(self.comments[identifier], name)

    @staticmethod
    def _span(comment: Comment, name: str) -> None:
        if name not in comment.spans:
            comment.spans.append(name)

    def _run(self, node: etree._Element) -> None:
        text = "".join(t.text or "" for t in node.iter(_q("t")))
        props = node.find(_q("rPr"))
        if props is not None and text.strip():
            for tag, kind in (("b", "bold"), ("i", "italic")):
                flag = props.find(_q(tag))
                if flag is not None and flag.get(_q("val")) not in ("0", "false"):
                    self.hints.append((kind, text, None))
            colour = props.find(_q("color"))
            value = (colour.get(_q("val")) or "") if colour is not None else ""
            if value and value.lower() != "auto":
                self.hints.append(("colour", text, value.upper()))
        self._children(node)

    def _paragraph(self, node: etree._Element) -> None:
        saved = (self.buffer, self.hints, self.touched)
        self.buffer, self.hints, self.touched = [], [], list(self.open.values())
        self._children(node)
        text = "".join(self.buffer).strip()
        section = self.touched[0] if self.touched else None
        listed = _is_list_item(node)
        if section is None and listed and text:
            section = self.listing
        self.listing = section if listed and section is not None else None
        if section is not None and _is_heading(node) and section not in self.result.titles:
            self.result.titles[section] = text
        elif text and section is not None:
            target = self.result.items if listed else self.result.paragraphs
            target.setdefault(section, []).append(text)
        elif text:
            self.result.unplaced.append((self.last, text))
        if section is not None:
            self.result.emphasis.setdefault(section, []).extend(self.hints)
        if section is not None:
            self.last = section
        self.buffer, self.hints, self.touched = saved

    def _place(self, identifier: str) -> None:
        """Attach a comment to the section it starts in, or where its reference sits if it has no range."""
        if identifier in self.comments and identifier not in self.placed:
            self.placed.add(identifier)
            self.result.comments.append((self.touched[0] if self.touched else None, self.comments[identifier]))

    def _children(self, node: etree._Element) -> None:
        for child in node:
            if not isinstance(child.tag, str):
                continue
            tag = etree.QName(child).localname
            if etree.QName(child).namespace != W:
                continue
            identifier = child.get(_q("id")) or ""
            if tag in SKIPPED:
                self.result.tracked = True
            elif tag in ("ins", "moveTo"):
                self.result.tracked = True
                self._children(child)
            elif tag == "bookmarkStart":
                raw = child.get(_q("name")) or ""
                name = section_of(raw, self.stored)
                if is_hashed(raw) and raw not in self.stored:
                    # An unresolved section cannot continue the preceding section's list.
                    self.listing = None
                    continue
                if self.known is None or name in self.known:
                    self.open[identifier] = name
                    self._start(name)
            elif tag == "bookmarkEnd":
                self.open.pop(identifier, None)
            elif tag == "commentRangeStart":
                self.ranges.add(identifier)
                self._place(identifier)
                if identifier in self.comments:
                    for name in self.open.values():
                        self._span(self.comments[identifier], name)
            elif tag == "commentRangeEnd":
                self.ranges.discard(identifier)
            elif tag == "commentReference":
                self._place(identifier)
            elif tag == "t":
                self._text(child.text or "")
            elif tag == "tab":
                self._text("\t")
            elif tag == "br":
                self._text("\n")
            elif tag == "p":
                self._paragraph(child)
            elif tag == "r":
                self._run(child)
            else:
                self._children(child)


def read_word(path: Path, sections: set[str] | None = None) -> WordText:
    """The applied text per section of a Word file: tracked insertions kept, tracked deletions dropped.

    `sections` names the bookmarks that count as sections; None counts every bookmark.
    """
    document, notes = _open(path)
    comments = _read_comments(notes)
    walker = _Walker(sections, comments, read_custom_properties(path))
    walker._children(document)
    result = walker.result
    return result
