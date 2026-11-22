"""Every section id comes back from a Word copy through `review read`, however long or odd it is."""

import json
import re
import zipfile

import pytest
from lxml import etree

from ai_docs_kit.cli import main

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CUSTOM = "docProps/custom.xml"


def _q(tag: str) -> str:
    return f"{{{W}}}{tag}"


def _source(section_id: str) -> str:
    return (
        "---\ndoctype: report\nformat: doc\ntitle: Note\n---\n\n"
        f'::: {{#{section_id} .section intent="body"}}\n## Opening\n\nOriginal wording of the section.\n:::\n'
    )


def _sent(tmp_path, section_id: str):
    (tmp_path / "report.md").write_text(_source(section_id), encoding="utf-8")
    assert main(["build", str(tmp_path / "report.md")]) == 0
    version = tmp_path / "report.versions" / "v1"
    empty = tmp_path / "none.json"
    empty.write_text("[]")
    assert main(["look", str(version), "--findings", str(empty)]) == 0
    return version / "report.docx"


def _rewrite(source, target, change=None, drop=()):
    with zipfile.ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    for name in drop:
        parts.pop(name, None)
    if change is not None:
        root = etree.fromstring(parts["word/document.xml"])
        change(root)
        parts["word/document.xml"] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)


def _reword(root) -> None:
    for t in root.iter(_q("t")):
        if "Original wording" in (t.text or ""):
            t.text = t.text.replace("Original", "Changed")


@pytest.mark.parametrize("section_id", ["my-section", "1st", "a" * 41, "é" * 10, "Xenc_x"])
def test_review_read_returns_the_section_id(tmp_path, capsys, section_id):
    sent = _sent(tmp_path, section_id)
    copy = tmp_path / "report-reviewed.docx"
    _rewrite(sent, copy, _reword)
    capsys.readouterr()
    assert main(["review", "read", str(copy)]) == 0
    plan = (
        json.loads((sent.parent / "review-plan.json").read_text(encoding="utf-8"))
        if (sent.parent / "review-plan.json").is_file()
        else None
    )
    if plan is None:
        plan = json.loads(next(sent.parent.glob("*plan*.json")).read_text(encoding="utf-8"))
    assert list(plan["sections"]) == [section_id]
    assert "Changed wording" in plan["sections"][section_id]["wording"]
    assert not [item for item in plan.get("confirm", []) if item.get("kind") == "unplaced"]


@pytest.mark.parametrize("section_id", ["my-section", "1st", "a" * 41, "é" * 10, "Xenc_x"])
def test_the_copy_writes_only_names_word_accepts(tmp_path, section_id):
    sent = _sent(tmp_path, section_id)
    with zipfile.ZipFile(sent) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    names = [n.get(_q("name")) for n in root.iter(_q("bookmarkStart"))]
    assert names
    for name in names:
        assert len(name) <= 40 and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name), name


def test_the_copy_stores_the_map_from_a_short_name_to_the_id(tmp_path):
    section_id = "a" * 41
    sent = _sent(tmp_path, section_id)
    with zipfile.ZipFile(sent) as archive:
        document = etree.fromstring(archive.read("word/document.xml"))
        custom = archive.read(CUSTOM).decode("utf-8")
    (name,) = [n.get(_q("name")) for n in document.iter(_q("bookmarkStart"))]
    assert name.startswith("Xh_")
    assert name in custom and section_id in custom


def test_a_hashed_name_missing_from_the_stored_map_is_unplaced_not_an_error(tmp_path):
    from ai_docs_kit.review.word_read import read_word

    sent = _sent(tmp_path, "a" * 41)

    def rename(root) -> None:
        for mark in root.iter(_q("bookmarkStart")):
            mark.set(_q("name"), "Xh_00000000")
        _reword(root)

    copy = tmp_path / "lost.docx"
    _rewrite(sent, copy, rename, drop=[CUSTOM])
    try:
        text = read_word(copy)
    except Exception as error:  # noqa: BLE001
        raise AssertionError(f"read_word raised instead of reporting the text as unplaced: {error!r}") from error
    assert "Xh_00000000" not in text.order
    assert any("Changed wording" in words for _, words in text.unplaced)
