"""`review read` on a Word copy: the plan keyed by section, and the schema that describes it.

Plan shape these tests pin (recorded under Deviations in PLAN.md):
`version` (int); `sections[<id>]` with `wording` (the applied text, `None` when unchanged),
`owner`, `confirm` (comment items: `kind`, `author`, `text`, `anchor`) and `emphasis`
(`kind` of bold, italic or colour, plus `text`); top-level `confirm` (kinds `delete`, `reorder`,
`unplaced`) and `warnings` (each with a `code`). The copy sits beside the working file.
"""

import json
import shutil
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from ai_docs_kit.cli import main

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}
SCHEMA = Path(__file__).resolve().parents[1] / "docs" / "schemas" / "review" / "ReviewPlan.schema.json"

SOURCE = """---
doctype: report
format: doc
title: Note
---

::: {#alpha01 .section intent="body"}
## Alpha

Alpha keeps its original wording here.
:::

::: {#beta01 .section intent="body"}
## Beta

Beta holds the second paragraph of the note.
:::

::: {#gamma01 .section intent="body"}
## Gamma

Gamma closes the note with a last paragraph.
:::
"""


def _run(argv: list[str]) -> int:
    try:
        return main(argv)
    except SystemExit as error:  # an unknown command must fail an assertion, not error
        return error.code if isinstance(error.code, int) else -1


@pytest.fixture(scope="module")
def sent(tmp_path_factory) -> Path:
    folder = tmp_path_factory.mktemp("sent")
    (folder / "report.md").write_text(SOURCE, encoding="utf-8")
    assert main(["build", str(folder / "report.md")]) == 0
    version = folder / "report.versions" / "v1"
    empty = folder / "none.json"
    empty.write_text("[]")
    assert main(["look", str(version), "--findings", str(empty)]) == 0
    assert main(["sent", str(version), "--to", "Reviewer"]) == 0
    assert (version / "report.docx").is_file()
    return folder


@pytest.fixture
def work(sent, tmp_path) -> Path:
    shutil.copytree(sent, tmp_path / "w")
    return tmp_path / "w"


def _copy(work: Path, change=None, comments=None) -> Path:
    """A review copy beside the working file: the sent Word copy with `change(root)` applied."""
    source = work / "report.versions" / "v1" / "report.docx"
    target = work / "report-reviewed.docx"
    with zipfile.ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    if change is not None:
        root = etree.fromstring(parts["word/document.xml"])
        change(root)
        parts["word/document.xml"] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    if comments:
        from docx import Document

        document = Document(str(target))
        for needle, author, text in comments:
            run = next(r for p in document.paragraphs for r in p.runs if needle in r.text)
            document.add_comment(run, text=text, author=author)
        document.save(str(target))
    return target


def _q(tag: str) -> str:
    return f"{{{W}}}{tag}"


def _paragraph(root, needle: str):
    found = [p for p in root.iter(_q("p")) if needle in "".join(p.itertext())]
    assert found, f"no paragraph with {needle!r}"
    return found[0]


def _run_with(root, needle: str):
    found = [r for r in root.iter(_q("r")) if needle in "".join(t.text or "" for t in r.iter(_q("t")))]
    assert found, f"no run with {needle!r}"
    return found[0]


def _replace_text(root, old: str, new: str) -> None:
    for t in root.iter(_q("t")):
        if old in (t.text or ""):
            t.text = t.text.replace(old, new)
            return
    raise AssertionError(f"no text {old!r}")


def _tracked(tag: str, run, author="Reviewer A"):
    wrapper = etree.Element(_q(tag))
    wrapper.set(_q("id"), "9001")
    wrapper.set(_q("author"), author)
    wrapper.set(_q("date"), "2026-11-17T09:00:00Z")
    run.addprevious(wrapper)
    wrapper.append(run)
    return wrapper


def _insert_after(root, needle: str, text: str) -> None:
    run = _run_with(root, needle)
    new = etree.Element(_q("r"))
    etree.SubElement(new, _q("t")).text = text
    wrapper = etree.Element(_q("ins"))
    for key, value in (("id", "9002"), ("author", "Reviewer A"), ("date", "2026-11-17T09:00:00Z")):
        wrapper.set(_q(key), value)
    wrapper.append(new)
    run.addnext(wrapper)


def _delete_words(root, needle: str, words: str) -> None:
    run = _run_with(root, needle)
    text = "".join(t.text or "" for t in run.iter(_q("t")))
    head, tail = text.split(words, 1)
    for t in list(run.iter(_q("t"))):
        t.getparent().remove(t)
    etree.SubElement(run, _q("t")).text = head
    removed = etree.Element(_q("r"))
    etree.SubElement(removed, _q("delText")).text = words
    after = etree.Element(_q("r"))
    etree.SubElement(after, _q("t")).text = tail
    wrapper = etree.Element(_q("del"))
    for key, value in (("id", "9003"), ("author", "Reviewer A"), ("date", "2026-11-17T09:00:00Z")):
        wrapper.set(_q(key), value)
    wrapper.append(removed)
    run.addnext(wrapper)
    wrapper.addnext(after)


def _read(work: Path, copy: Path, capsys) -> tuple[int, str, str, dict | None]:
    code = _run(["review", "read", str(copy)])
    out = capsys.readouterr()
    plan = None
    for line in out.out.splitlines():
        candidate = Path(line.strip().split()[-1]) if line.strip() else None
        if candidate is not None and candidate.suffix == ".json" and candidate.is_file():
            plan = json.loads(candidate.read_text(encoding="utf-8"))
    return code, out.out, out.err, plan


def _plan(work: Path, copy: Path, capsys) -> dict:
    code, out, err, plan = _read(work, copy, capsys)
    assert code == 0, err
    assert plan is not None, f"no plan path printed in {out!r}"
    return plan


def _section(plan: dict, name: str) -> dict:
    return plan["sections"].get(name) or {}


def _kinds(items) -> list[str]:
    return [item["kind"] for item in items or []]


def test_the_plan_schema_is_committed_and_names_the_plan_parts():
    assert SCHEMA.is_file(), f"no schema at {SCHEMA}"
    text = SCHEMA.read_text(encoding="utf-8")
    json.loads(text)
    for word in ("version", "sections", "wording", "confirm", "emphasis", "warnings"):
        assert word in text, word
    for kind in ("comment", "delete", "reorder", "unplaced"):
        assert kind in text, kind


def test_the_plan_is_written_to_the_version_folder_with_a_one_screen_summary(work, capsys):
    copy = _copy(work, lambda root: _replace_text(root, "original wording", "revised wording"))
    code, out, err, plan = _read(work, copy, capsys)
    assert code == 0, err
    assert plan is not None
    paths = [line.split()[-1] for line in out.splitlines() if line.strip().endswith(".json")]
    assert paths and Path(paths[-1]).parent == work / "report.versions" / "v1"
    assert len(out.splitlines()) <= 24
    assert "alpha01" in out


def test_the_plan_compares_with_the_latest_version_not_a_later_build(work, capsys):
    assert main(["build", str(work / "report.md")]) == 0
    assert (work / "report.versions" / "v2").is_dir()
    copy = _copy(work, lambda root: _replace_text(root, "original wording", "revised wording"))
    plan = _plan(work, copy, capsys)
    assert plan["version"] == 1


def test_a_plain_text_edit_is_applied_to_its_section_only(work, capsys):
    copy = _copy(work, lambda root: _replace_text(root, "original wording", "revised wording"))
    plan = _plan(work, copy, capsys)
    assert "Alpha keeps its revised wording here." in _section(plan, "alpha01")["wording"]
    assert _section(plan, "beta01").get("wording") is None
    assert _section(plan, "gamma01").get("wording") is None
    assert not [w for w in plan["warnings"] if w["code"] == "tracking_warning"]


def test_a_tracked_insertion_is_applied_to_its_section(work, capsys):
    copy = _copy(work, lambda root: _insert_after(root, "second paragraph", " It also adds a clause."))
    plan = _plan(work, copy, capsys)
    assert "It also adds a clause." in _section(plan, "beta01")["wording"]
    assert _section(plan, "alpha01").get("wording") is None


def test_a_tracked_deletion_is_left_out_of_the_applied_wording(work, capsys):
    copy = _copy(work, lambda root: _delete_words(root, "last paragraph", " with a last paragraph"))
    plan = _plan(work, copy, capsys)
    wording = _section(plan, "gamma01")["wording"]
    assert "Gamma closes the note." in wording
    assert "last paragraph" not in wording


def test_a_comment_becomes_a_confirm_item_on_its_section_with_anchor_and_author(work, capsys):
    copy = _copy(work, comments=[("second paragraph", "Reviewer B", "Say how many readings drop.")])
    plan = _plan(work, copy, capsys)
    items = _section(plan, "beta01")["confirm"]
    assert _kinds(items) == ["comment"]
    assert items[0]["author"] == "Reviewer B"
    assert "Say how many readings drop." in items[0]["text"]
    assert "second paragraph" in items[0]["anchor"]
    assert _section(plan, "alpha01").get("wording") is None
    assert not _section(plan, "alpha01").get("confirm")


def test_a_comment_gives_no_wording_change(work, capsys):
    copy = _copy(work, comments=[("second paragraph", "Reviewer B", "Say how many.")])
    plan = _plan(work, copy, capsys)
    assert _section(plan, "beta01").get("wording") is None


@pytest.mark.parametrize("kind", ["bold", "italic", "colour"])
def test_formatting_gives_an_emphasis_hint_and_no_wording_change(work, capsys, kind):
    def change(root):
        run = _run_with(root, "second paragraph")
        props = run.find("w:rPr", NS)
        if props is None:
            props = etree.Element(_q("rPr"))
            run.insert(0, props)
        if kind == "colour":
            etree.SubElement(props, _q("color")).set(_q("val"), "FF0000")
        else:
            etree.SubElement(props, _q("b" if kind == "bold" else "i"))

    plan = _plan(work, _copy(work, change), capsys)
    beta = _section(plan, "beta01")
    assert beta.get("wording") is None
    assert kind in _kinds(beta.get("emphasis"))
    assert "second paragraph" in " ".join(item["text"] for item in beta["emphasis"])


def test_a_copy_identical_to_the_sent_one_gives_a_tracking_warning(work, capsys):
    plan = _plan(work, _copy(work), capsys)
    assert "tracking_warning" in [w["code"] for w in plan["warnings"]]
    assert not [s for s in plan["sections"].values() if s.get("wording") or s.get("confirm")]
    assert not plan.get("confirm")


def test_a_deleted_section_is_a_structural_confirm_item(work, capsys):
    def change(root):
        body = root.find("w:body", NS)
        start = next(b for b in root.iter(_q("bookmarkStart")) if b.get(_q("name")) == "beta01")
        marker = start.get(_q("id"))
        end = next(b for b in root.iter(_q("bookmarkEnd")) if b.get(_q("id")) == marker)
        top = [c for c in body]

        def owner(node):
            while node.getparent() is not body:
                node = node.getparent()
            return node

        first, last = top.index(owner(start)), top.index(owner(end))
        for node in top[first : last + 1]:
            body.remove(node)

    plan = _plan(work, _copy(work, change), capsys)
    deleted = [c for c in plan["confirm"] if c["kind"] == "delete"]
    assert [c["section"] for c in deleted] == ["beta01"]


def test_a_reordered_section_is_a_structural_confirm_item(work, capsys):
    def change(root):
        body = root.find("w:body", NS)
        top = list(body)

        def owner(name):
            start = next(b for b in root.iter(_q("bookmarkStart")) if b.get(_q("name")) == name)
            node = start
            while node.getparent() is not body:
                node = node.getparent()
            return top.index(node)

        gamma, beta = owner("gamma01"), owner("beta01")
        moved = top[gamma:]
        sect = body.find("w:sectPr", NS)
        if sect is not None and sect in moved:
            moved.remove(sect)
        for node in moved:
            body.remove(node)
        for offset, node in enumerate(moved):
            body.insert(beta + offset, node)

    plan = _plan(work, _copy(work, change), capsys)
    assert "reorder" in _kinds(plan["confirm"])


def test_text_outside_every_section_is_an_unplaced_confirm_item(work, capsys):
    def change(root):
        last = next(b for b in reversed(list(root.iter(_q("bookmarkEnd")))))
        node = last
        body = root.find("w:body", NS)
        while node.getparent() is not body:
            node = node.getparent()
        extra = etree.Element(_q("p"))
        run = etree.SubElement(extra, _q("r"))
        etree.SubElement(run, _q("t")).text = "A stray closing remark from the reviewer."
        node.addnext(extra)

    plan = _plan(work, _copy(work, change), capsys)
    unplaced = [c for c in plan["confirm"] if c["kind"] == "unplaced"]
    assert len(unplaced) == 1
    assert "stray closing remark" in unplaced[0]["text"]


def test_reading_twice_gives_the_same_plan(work, capsys):
    copy = _copy(work, lambda root: _replace_text(root, "original wording", "revised wording"))
    assert _plan(work, copy, capsys) == _plan(work, copy, capsys)


def test_a_missing_copy_exits_two_with_a_message(work, capsys):
    code = _run(["review", "read", str(work / "nope.docx")])
    assert code == 2
    assert "nope.docx" in capsys.readouterr().err


def test_a_copy_that_is_not_an_archive_exits_two_with_a_line(work, capsys):
    _plan(work, _copy(work), capsys)
    bad = work / "bad.docx"
    bad.write_text("not a zip")
    assert _run(["review", "read", str(bad)]) == 2
    err = capsys.readouterr().err.strip()
    assert err and "Traceback" not in err and len(err.splitlines()) == 1


def _hostile(work: Path, part: str, data) -> Path:
    good = _copy(work)
    target = work / "hostile.docx"
    with zipfile.ZipFile(good) as source, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in source.namelist():
            if name != part:
                archive.writestr(name, source.read(name))
        if isinstance(data, bytes):
            archive.writestr(part, data)
        else:
            with archive.open(part, "w", force_zip64=True) as handle:
                for chunk in data:
                    handle.write(chunk)
    return target


def _refused(work: Path, capsys, copy: Path) -> None:
    _plan(work, _copy(work), capsys)  # the unmodified copy reads, so only the hostile part can fail
    assert _run(["review", "read", str(copy)]) == 2
    err = capsys.readouterr().err.strip()
    assert err and "Traceback" not in err


def test_an_oversized_part_is_refused(work, capsys):
    head = b'<?xml version="1.0"?><w:document xmlns:w="%s"><w:body><w:p><w:r><w:t>' % W.encode()
    chunks = [head] + [b" " * (1 << 20)] * 400 + [b"</w:t></w:r></w:p></w:body></w:document>"]
    _refused(work, capsys, _hostile(work, "word/document.xml", chunks))


def test_too_many_entries_are_refused(work, capsys):
    copy = _copy(work)
    shutil.copyfile(copy, work / "many.docx")
    with zipfile.ZipFile(work / "many.docx", "a") as archive:
        for number in range(20000):
            archive.writestr(f"extra/{number}.txt", b"x")
    _plan(work, _copy(work), capsys)
    assert _run(["review", "read", str(work / "many.docx")]) == 2
    assert "Traceback" not in capsys.readouterr().err


def test_deeply_nested_xml_is_refused(work, capsys):
    depth = 20000
    data = (
        b'<?xml version="1.0"?><w:document xmlns:w="%s"><w:body>' % W.encode()
        + b"<w:p>" * depth
        + b"</w:p>" * depth
        + b"</w:body></w:document>"
    )
    _refused(work, capsys, _hostile(work, "word/document.xml", data))


def test_an_external_entity_is_not_resolved(work, capsys):
    secret = work / "secret.txt"
    secret.write_text("SECRET-TOKEN-4417")
    data = (
        f'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file://{secret}">]>'
        f'<w:document xmlns:w="{W}"><w:body><w:p><w:bookmarkStart w:id="1" w:name="alpha01"/>'
        '<w:r><w:t>&x;</w:t></w:r><w:bookmarkEnd w:id="1"/></w:p></w:body></w:document>'
    ).encode()
    copy = _hostile(work, "word/document.xml", data)
    _plan(work, _copy(work), capsys)
    code = _run(["review", "read", str(copy)])
    out = capsys.readouterr()
    assert code in (0, 2)
    assert "SECRET-TOKEN-4417" not in out.out + out.err
    for plan_file in (work / "report.versions" / "v1").glob("*.json"):
        assert "SECRET-TOKEN-4417" not in plan_file.read_text(encoding="utf-8")
