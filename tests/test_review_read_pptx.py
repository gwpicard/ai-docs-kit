"""`review read` on a PowerPoint copy: the same plan as the Word reader, built from slides.

Plan shape these tests pin (recorded under Deviations in PLAN.md), on top of the Word plan:
a changed text box named `<section-id>/<field-path>` gives `sections[<id>]["fields"][<path>]`, the
applied text of that field, and `owner` "human"; formatting gives `emphasis` hints; a comment item
carries `slide` (1-based, in the sent deck's order) and `shape` (the shape name, or None) beside
`author`, `text` and `anchor`, and sits on the section whose text boxes are on that slide.
Structure items: `delete` (with `section`), `reorder` and `unplaced`, as in the Word plan.
"""

import json
import shutil
import zipfile
from pathlib import Path

import pytest
from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from tests.support.fixtures import fixture_path

from ai_docs_kit.cli import main

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
P188 = "http://schemas.microsoft.com/office/powerpoint/2018/8/main"
PC = "http://schemas.microsoft.com/office/powerpoint/2013/main/command"
AC = "http://schemas.microsoft.com/office/drawing/2013/main/command"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
LEGACY_REL = f"{R}/comments"
LEGACY_AUTHORS_REL = f"{R}/commentAuthors"
MODERN_REL = "http://schemas.microsoft.com/office/2018/10/relationships/comments"
MODERN_AUTHORS_REL = "http://schemas.microsoft.com/office/2018/10/relationships/authors"
OFFICE = "application/vnd.openxmlformats-officedocument.presentationml"
SCHEMA = Path(__file__).resolve().parents[1] / "docs" / "schemas" / "review" / "ReviewPlan.schema.json"


def _run(argv: list[str]) -> int:
    try:
        return main(argv)
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else -1


@pytest.fixture(scope="module")
def sent(tmp_path_factory) -> Path:
    folder = tmp_path_factory.mktemp("sentdeck")
    shutil.copyfile(fixture_path("slides", "deck.md"), folder / "deck.md")
    assert main(["build", str(folder / "deck.md")]) == 0
    version = folder / "deck.versions" / "v1"
    empty = folder / "none.json"
    empty.write_text("[]")
    assert main(["look", str(version), "--findings", str(empty)]) == 0
    assert main(["sent", str(version), "--to", "Reviewer"]) == 0
    assert (version / "deck.pptx").is_file()
    return folder


@pytest.fixture
def work(sent, tmp_path) -> Path:
    shutil.copytree(sent, tmp_path / "w")
    return tmp_path / "w"


def _shape(slide, name: str):
    found = [s for s in slide.shapes if s.name == name]
    assert found, f"no shape {name!r}"
    return found[0]


def _deck_copy(work: Path, change=None, parts: dict[str, bytes] | None = None, name="deck-reviewed.pptx") -> Path:
    """A review copy beside the working file: the sent deck with `change(presentation)` applied,
    then `parts` (name -> bytes) added to or replacing the archive's parts."""
    source = work / "deck.versions" / "v1" / "deck.pptx"
    target = work / name
    shutil.copyfile(source, target)
    if change is not None:
        deck = Presentation(str(target))
        change(deck)
        deck.save(str(target))
    if parts:
        with zipfile.ZipFile(target) as archive:
            existing = {n: archive.read(n) for n in archive.namelist()}
        existing.update(parts)
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            for n, data in existing.items():
                archive.writestr(n, data)
    return target


def _read(copy: Path, capsys) -> tuple[int, str, str, dict | None]:
    code = _run(["review", "read", str(copy)])
    out = capsys.readouterr()
    plan = None
    for line in out.out.splitlines():
        candidate = Path(line.strip().split()[-1]) if line.strip() else None
        if candidate is not None and candidate.suffix == ".json" and candidate.is_file():
            plan = json.loads(candidate.read_text(encoding="utf-8"))
    return code, out.out, out.err, plan


def _plan(copy: Path, capsys) -> dict:
    code, out, err, plan = _read(copy, capsys)
    assert code == 0, err
    assert plan is not None, f"no plan path printed in {out!r}"
    return plan


def _section(plan: dict, name: str) -> dict:
    return plan["sections"].get(name) or {}


def _kinds(items) -> list[str]:
    return [item["kind"] for item in items or []]


def _set_text(shape, text: str) -> None:
    runs = [r for p in shape.text_frame.paragraphs for r in p.runs]
    runs[0].text = text
    for extra in runs[1:]:
        extra.text = ""


def _slide_ids(deck) -> list[int]:
    return [int(s.get("id")) for s in deck.part._element.iter(f"{{{P}}}sldId")]


def _xml(root: etree._Element) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _rels_for(work: Path, copy_part: str, extra: list[tuple[str, str, str]], source: Path | None = None) -> bytes:
    """The `.rels` file of `copy_part` in the sent deck, plus `extra` (id, type, target) relationships."""
    path = source or work / "deck.versions" / "v1" / "deck.pptx"
    folder, _, base = copy_part.rpartition("/")
    rels_name = f"{folder}/_rels/{base}.rels"
    with zipfile.ZipFile(path) as archive:
        root = (
            etree.fromstring(archive.read(rels_name))
            if rels_name in archive.namelist()
            else etree.Element(f"{{{PKG_REL}}}Relationships", nsmap={None: PKG_REL})
        )
    for rid, kind, target in extra:
        etree.SubElement(root, f"{{{PKG_REL}}}Relationship", Id=rid, Type=kind, Target=target)
    return _xml(root)


def _content_types(work: Path, overrides: dict[str, str], base: Path | None = None) -> bytes:
    with zipfile.ZipFile(base or work / "deck.versions" / "v1" / "deck.pptx") as archive:
        root = etree.fromstring(archive.read("[Content_Types].xml"))
    for part, kind in overrides.items():
        etree.SubElement(root, f"{{{CT}}}Override", PartName=f"/{part}", ContentType=kind)
    return _xml(root)


def _legacy_parts(work: Path, slide: int, author: str, text: str, base: Path | None = None) -> dict[str, bytes]:
    """A legacy comment on slide number `slide` (1-based): commentAuthors.xml and comment1.xml."""
    authors = (
        f'<p:cmAuthorLst xmlns:p="{P}"><p:cmAuthor id="0" name="{author}" initials="LA" lastIdx="1" clrIdx="0"/>'
        "</p:cmAuthorLst>"
    )
    comment = (
        f'<p:cmLst xmlns:p="{P}"><p:cm authorId="0" dt="2026-11-17T09:00:00.000" idx="1">'
        f'<p:pos x="10" y="10"/><p:text>{text}</p:text></p:cm></p:cmLst>'
    )
    src = base or work / "deck.versions" / "v1" / "deck.pptx"
    with zipfile.ZipFile(src) as archive:
        presentation = etree.fromstring(archive.read("ppt/presentation.xml"))
        rels = etree.fromstring(archive.read("ppt/_rels/presentation.xml.rels"))
    targets = {r.get("Id"): r.get("Target") for r in rels}
    first = presentation.findall(f".//{{{P}}}sldId")[slide - 1]
    slide_part = "ppt/" + targets[first.get(f"{{{R}}}id")]
    return {
        "ppt/commentAuthors.xml": authors.encode(),
        "ppt/comments/comment1.xml": comment.encode(),
        "ppt/_rels/presentation.xml.rels": _rels_for(
            work, "ppt/presentation.xml", [("rIdLegAuth", LEGACY_AUTHORS_REL, "commentAuthors.xml")], src
        ),
        slide_part.replace("slides/", "slides/_rels/") + ".rels": _rels_for(
            work, slide_part, [("rIdLegCm", LEGACY_REL, "../comments/comment1.xml")], src
        ),
        "[Content_Types].xml": _content_types(
            work,
            {
                "ppt/commentAuthors.xml": f"{OFFICE}.commentAuthors+xml",
                "ppt/comments/comment1.xml": f"{OFFICE}.comments+xml",
            },
            src,
        ),
    }


def _modern_parts(
    work: Path, slide: int, author: str, text: str, shape: str | None, base: Path | None = None
) -> dict[str, bytes]:
    """A modern comment on slide number `slide`, on shape `shape` (a name) when given."""
    src = base or work / "deck.versions" / "v1" / "deck.pptx"
    deck = Presentation(str(src))
    ids = _slide_ids(deck)
    target = deck.slides[slide - 1]
    anchor = ""
    if shape is not None:
        shape_id = _shape(target, shape).shape_id
        anchor = (
            f'<ac:deMkLst xmlns:ac="{AC}"><pc:docMk xmlns:pc="{PC}"/>'
            f'<pc:sldMk xmlns:pc="{PC}" cId="1" sldId="{ids[slide - 1]}"/>'
            f'<ac:spMk id="{shape_id}" creationId="{{00000000-0000-0000-0000-000000000001}}"/></ac:deMkLst>'
        )
    else:
        anchor = f'<pc:sldMkLst xmlns:pc="{PC}"><pc:docMk/><pc:sldMk cId="1" sldId="{ids[slide - 1]}"/></pc:sldMkLst>'
    comment = (
        f'<p188:cmLst xmlns:a="{A}" xmlns:r="{R}" xmlns:p188="{P188}">'
        f'<p188:cm id="{{11111111-1111-1111-1111-111111111111}}" authorId="{{22222222-2222-2222-2222-222222222222}}"'
        f' created="2026-11-17T09:00:00.000">{anchor}'
        f'<p188:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr lang="en-GB"/><a:t>{text}</a:t></a:r></a:p>'
        "</p188:txBody></p188:cm></p188:cmLst>"
    )
    authors = (
        f'<p188:authorLst xmlns:a="{A}" xmlns:r="{R}" xmlns:p188="{P188}">'
        f'<p188:author id="{{22222222-2222-2222-2222-222222222222}}" name="{author}" initials="MA"'
        ' userId="S::ma@example.test::1" providerId="AD"/></p188:authorLst>'
    )
    with zipfile.ZipFile(src) as archive:
        rels = etree.fromstring(archive.read("ppt/_rels/presentation.xml.rels"))
        presentation = etree.fromstring(archive.read("ppt/presentation.xml"))
    targets = {r.get("Id"): r.get("Target") for r in rels}
    first = presentation.findall(f".//{{{P}}}sldId")[slide - 1]
    slide_part = "ppt/" + targets[first.get(f"{{{R}}}id")]
    return {
        "ppt/authors.xml": authors.encode(),
        "ppt/comments/modernComment_100_1.xml": comment.encode(),
        "ppt/_rels/presentation.xml.rels": _rels_for(
            work, "ppt/presentation.xml", [("rIdModAuth", MODERN_AUTHORS_REL, "authors.xml")], src
        ),
        slide_part.replace("slides/", "slides/_rels/") + ".rels": _rels_for(
            work, slide_part, [("rIdModCm", MODERN_REL, "../comments/modernComment_100_1.xml")], src
        ),
        "[Content_Types].xml": _content_types(
            work,
            {
                "ppt/authors.xml": "application/vnd.ms-powerpoint.authors+xml",
                "ppt/comments/modernComment_100_1.xml": "application/vnd.ms-powerpoint.comments+xml",
            },
            src,
        ),
    }


def test_the_plan_schema_still_names_the_plan_parts():
    text = SCHEMA.read_text(encoding="utf-8")
    for word in ("version", "sections", "wording", "confirm", "emphasis", "warnings"):
        assert word in text, word


def test_the_pptx_plan_has_the_word_plan_shape_and_is_written_to_the_version_folder(work, capsys):
    copy = _deck_copy(work, lambda d: _set_text(_shape(d.slides[2], "statement/text"), "A sharper direction"))
    code, out, err, plan = _read(copy, capsys)
    assert code == 0, err
    assert plan is not None
    assert plan["version"] == 1
    assert plan["review_copy"] == copy.name
    assert set(plan["sections"]) >= {"cover", "agenda", "statement", "closing"}
    paths = [line.split()[-1] for line in out.splitlines() if line.strip().endswith(".json")]
    assert paths and Path(paths[-1]).parent == work / "deck.versions" / "v1"
    assert len(out.splitlines()) <= 24
    assert "statement" in out


@pytest.mark.parametrize(
    ("slide", "name", "old", "new"),
    [
        (2, "statement/text", "A clear direction", "A sharper direction"),
        (0, "cover/paragraphs[0]", "A short deck for build tests.", "A reworded deck line."),
        (1, "agenda/items[1].body", "Review the options [S1]", "Compare the three options [S1]"),
    ],
)
def test_a_changed_text_box_is_applied_to_its_field_and_no_other(work, capsys, slide, name, old, new):
    def change(deck):
        shape = _shape(deck.slides[slide], name)
        assert shape.text_frame.text == old
        _set_text(shape, new)

    plan = _plan(_deck_copy(work, change), capsys)
    section, path = name.split("/", 1)
    assert _section(plan, section)["fields"] == {path: new}
    assert _section(plan, section)["owner"] == "human"
    for other, item in plan["sections"].items():
        if other != section:
            assert not item.get("fields")
            assert item.get("owner") is None
    assert not [w for w in plan["warnings"] if w["code"] == "tracking_warning"]


def test_two_changed_boxes_in_one_section_are_both_applied(work, capsys):
    def change(deck):
        _set_text(_shape(deck.slides[1], "agenda/title"), "Our agenda")
        _set_text(_shape(deck.slides[1], "agenda/items[2].body"), "Agree next steps [S1]")

    plan = _plan(_deck_copy(work, change), capsys)
    assert _section(plan, "agenda")["fields"] == {
        "title": "Our agenda",
        "items[2].body": "Agree next steps [S1]",
    }


@pytest.mark.parametrize("kind", ["bold", "italic", "colour"])
def test_formatting_gives_an_emphasis_hint_and_no_applied_text(work, capsys, kind):
    def change(deck):
        font = _shape(deck.slides[2], "statement/text").text_frame.paragraphs[0].runs[0].font
        if kind == "bold":
            font.bold = True
        elif kind == "italic":
            font.italic = True
        else:
            font.color.rgb = RGBColor(0xFF, 0x00, 0x00)

    plan = _plan(_deck_copy(work, change), capsys)
    item = _section(plan, "statement")
    assert not item.get("fields")
    assert item.get("owner") is None
    assert kind in _kinds(item.get("emphasis"))
    assert "A clear direction" in " ".join(hint["text"] for hint in item["emphasis"])
    assert not _section(plan, "cover").get("emphasis")


def test_legacy_comment_is_anchored_to_its_slide(work, capsys):
    copy = _deck_copy(work, parts=_legacy_parts(work, 3, "Legacy Author", "Name the direction."))
    plan = _plan(copy, capsys)
    items = _section(plan, "statement")["confirm"]
    assert _kinds(items) == ["comment"]
    assert items[0]["author"] == "Legacy Author"
    assert "Name the direction." in items[0]["text"]
    assert items[0]["slide"] == 3
    assert items[0]["shape"] is None
    assert not _section(plan, "cover").get("confirm")
    assert not _section(plan, "statement").get("fields")


def test_modern_comment_is_anchored_to_its_slide_and_shape(work, capsys):
    copy = _deck_copy(work, parts=_modern_parts(work, 2, "Modern Author", "Is this the right order?", "agenda/title"))
    plan = _plan(copy, capsys)
    items = _section(plan, "agenda")["confirm"]
    assert _kinds(items) == ["comment"]
    assert items[0]["author"] == "Modern Author"
    assert "Is this the right order?" in items[0]["text"]
    assert items[0]["slide"] == 2
    assert items[0]["shape"] == "agenda/title"
    assert "agenda/title" in items[0]["anchor"]


def test_modern_comment_on_a_slide_alone_has_no_shape(work, capsys):
    copy = _deck_copy(work, parts=_modern_parts(work, 1, "Modern Author", "Lead with the date.", None))
    items = _section(_plan(copy, capsys), "cover")["confirm"]
    assert [(i["slide"], i["shape"]) for i in items] == [(1, None)]


def test_one_file_holding_both_comment_formats_is_read_in_full(work, capsys):
    legacy = _legacy_parts(work, 1, "Legacy Author", "Old-style note.")
    modern = _modern_parts(work, 4, "Modern Author", "New-style note.", "closing/title")
    # Both edit presentation.xml.rels and [Content_Types].xml, so merge those two by hand.
    rels = etree.fromstring(legacy["ppt/_rels/presentation.xml.rels"])
    for rel in etree.fromstring(modern["ppt/_rels/presentation.xml.rels"]):
        if rel.get("Id") not in {r.get("Id") for r in rels}:
            rels.append(rel)
    types = etree.fromstring(legacy["[Content_Types].xml"])
    seen = {o.get("PartName") for o in types}
    for override in etree.fromstring(modern["[Content_Types].xml"]):
        if override.get("PartName") not in seen:
            types.append(override)
    merged = {**legacy, **modern, "ppt/_rels/presentation.xml.rels": _xml(rels), "[Content_Types].xml": _xml(types)}
    plan = _plan(_deck_copy(work, parts=merged, name="both.pptx"), capsys)
    cover = _section(plan, "cover")["confirm"]
    closing = _section(plan, "closing")["confirm"]
    assert [(i["author"], i["slide"], i["shape"]) for i in cover] == [("Legacy Author", 1, None)]
    assert [(i["author"], i["slide"], i["shape"]) for i in closing] == [("Modern Author", 4, "closing/title")]
    assert "Old-style note." in cover[0]["text"] and "New-style note." in closing[0]["text"]


def test_a_deleted_slide_is_a_confirm_item_naming_its_section(work, capsys):
    def change(deck):
        ids = deck.part._element.find(f"{{{P}}}sldIdLst")
        victim = ids[3]
        deck.part.drop_rel(victim.get(f"{{{R}}}id"))
        ids.remove(victim)

    plan = _plan(_deck_copy(work, change), capsys)
    deleted = [c for c in plan["confirm"] if c["kind"] == "delete"]
    assert [c["section"] for c in deleted] == ["closing"]
    assert not _section(plan, "closing").get("fields")
    assert not [c for c in plan["confirm"] if c["kind"] == "reorder"]


def test_a_reordered_deck_is_a_confirm_item_with_the_new_order(work, capsys):
    def change(deck):
        ids = deck.part._element.find(f"{{{P}}}sldIdLst")
        second = ids[1]
        ids.remove(second)
        ids.insert(2, second)  # cover, statement, agenda, closing

    plan = _plan(_deck_copy(work, change), capsys)
    reorders = [c for c in plan["confirm"] if c["kind"] == "reorder"]
    assert len(reorders) == 1
    assert reorders[0]["order"] == ["cover", "statement", "agenda", "closing"]
    assert not [c for c in plan["confirm"] if c["kind"] == "delete"]
    assert not any(item.get("fields") for item in plan["sections"].values())


def test_a_new_text_box_with_no_section_name_is_an_unplaced_confirm_item(work, capsys):
    def change(deck):
        box = deck.slides[2].shapes.add_textbox(0, 0, 3000000, 500000)
        box.text_frame.text = "A late idea from the reviewer."

    plan = _plan(_deck_copy(work, change), capsys)
    unplaced = [c for c in plan["confirm"] if c["kind"] == "unplaced"]
    assert len(unplaced) == 1
    assert "A late idea from the reviewer." in unplaced[0]["text"]
    assert not any(item.get("fields") for item in plan["sections"].values())


def test_a_copy_identical_to_the_sent_one_gives_a_tracking_warning(work, capsys):
    plan = _plan(_deck_copy(work), capsys)
    assert "tracking_warning" in [w["code"] for w in plan["warnings"]]
    assert not plan.get("confirm")
    assert not [s for s in plan["sections"].values() if s.get("fields") or s.get("confirm")]


def test_reading_twice_gives_the_same_plan(work, capsys):
    copy = _deck_copy(work, lambda d: _set_text(_shape(d.slides[2], "statement/text"), "A sharper direction"))
    assert _plan(copy, capsys) == _plan(copy, capsys)


def test_a_pptx_that_is_not_an_archive_exits_two_with_a_line(work, capsys):
    _plan(_deck_copy(work), capsys)
    bad = work / "bad.pptx"
    bad.write_text("not a zip")
    assert _run(["review", "read", str(bad)]) == 2
    err = capsys.readouterr().err.strip()
    assert err and "Traceback" not in err and len(err.splitlines()) == 1


def test_a_comment_part_with_an_external_entity_is_not_resolved(work, capsys):
    secret = work / "secret.txt"
    secret.write_text("SECRET-TOKEN-4417")
    hostile = (
        f'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file://{secret}">]>'
        f'<p:cmLst xmlns:p="{P}"><p:cm authorId="0" dt="2026-11-17T09:00:00.000" idx="1">'
        '<p:pos x="1" y="1"/><p:text>&x;</p:text></p:cm></p:cmLst>'
    ).encode()
    parts = _legacy_parts(work, 1, "Legacy Author", "x")
    parts["ppt/comments/comment1.xml"] = hostile
    copy = _deck_copy(work, parts=parts, name="hostile.pptx")
    _plan(_deck_copy(work), capsys)
    code = _run(["review", "read", str(copy)])
    out = capsys.readouterr()
    assert code in (0, 2)
    assert "SECRET-TOKEN-4417" not in out.out + out.err
    for plan_file in (work / "deck.versions" / "v1").glob("*.json"):
        assert "SECRET-TOKEN-4417" not in plan_file.read_text(encoding="utf-8")
