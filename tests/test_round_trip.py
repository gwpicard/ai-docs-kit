"""The whole round trip on fixtures, for both formats, with no model call.

A document is built, looked at, sent, and a review copy comes back with an edited field, a comment and a
deleted section. `review read`, a decision, `review apply`, a rebuild, a look and `sent` follow. The second
version holds the reviewer's words and no deleted section, and the working file holds a `redraft=` on the
commented section. The README carries the install steps and the five-minute live test.
"""

import json
import re
import shutil
import time
import zipfile
from pathlib import Path

import pytest
from docx import Document
from lxml import etree
from pptx import Presentation
from tests.support.fixtures import fixture_path

from ai_docs_kit.cli import main
from ai_docs_kit.source.parser import parse

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
OFFICE = "application/vnd.openxmlformats-officedocument.presentationml"
README = Path(__file__).resolve().parents[1] / "README.md"

DOC_SOURCE = """---
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

REVIEWER_WORDS = "A reworded line from the reviewer."
ASK = "say how many readings drop"


def _run(argv: list[str]) -> int:
    try:
        return main(argv)
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else -1


def _plan_path(out: str) -> Path:
    return Path([line.split()[-1] for line in out.splitlines() if line.strip().endswith(".json")][-1])


def _send(folder: Path, stem: str, version: str, capsys) -> Path:
    """Look at a built version (an empty agent look) and mark it sent."""
    folder_version = folder / f"{stem}.versions" / version
    empty = folder / f"none-{version}.json"
    empty.write_text("[]")
    assert main(["look", str(folder_version), "--findings", str(empty)]) == 0
    assert main(["sent", str(folder_version), "--to", "Reviewer"]) == 0
    capsys.readouterr()
    return folder_version


def _composition(version: Path) -> dict:
    return json.loads((version / "composition.json").read_text(encoding="utf-8"))


def _composition_text(version: Path) -> str:
    return json.dumps(_composition(version), ensure_ascii=False)


def _sections(path: Path) -> dict:
    doc, _ = parse(path.read_text(encoding="utf-8"))
    return {s.id: s for s in doc.sections}


def _decide(plan: dict, ask: str) -> dict:
    for section in plan["sections"].values():
        for item in section.get("confirm") or []:
            item.update(accepted=True, action="redraft", ask=ask)
    for item in plan["confirm"]:
        if item["kind"] == "delete":
            item.update(accepted=True, action="restructure")
    return plan


def _apply_and_rebuild(folder: Path, stem: str, plan: dict, capsys) -> Path:
    decided = folder / "decided.json"
    decided.write_text(json.dumps(plan), encoding="utf-8")
    assert main(["review", "apply", str(folder / f"{stem}.md"), "--plan", str(decided)]) == 0
    capsys.readouterr()
    assert main(["build", str(folder / f"{stem}.md")]) == 0
    capsys.readouterr()
    return _send(folder, stem, "v2", capsys)


def _read(copy: Path, capsys) -> dict:
    assert main(["review", "read", str(copy)]) == 0
    return json.loads(_plan_path(capsys.readouterr().out).read_text(encoding="utf-8"))


def _legacy_comment(deck_path: Path, slide: int, text: str) -> None:
    """Add a legacy comment on slide number `slide` (1-based) by writing the comment parts."""
    with zipfile.ZipFile(deck_path) as archive:
        parts = {n: archive.read(n) for n in archive.namelist()}
    presentation = etree.fromstring(parts["ppt/presentation.xml"])
    rels = etree.fromstring(parts["ppt/_rels/presentation.xml.rels"])
    targets = {r.get("Id"): r.get("Target") for r in rels}
    first = presentation.findall(f".//{{{P}}}sldId")[slide - 1]
    slide_part = "ppt/" + targets[first.get(f"{{{R}}}id")]
    slide_rels = slide_part.replace("slides/", "slides/_rels/") + ".rels"

    def add_rel(name: str, rel_id: str, kind: str, target: str) -> None:
        root = (
            etree.fromstring(parts[name])
            if name in parts
            else etree.Element(f"{{{PKG_REL}}}Relationships", nsmap={None: PKG_REL})
        )
        etree.SubElement(root, f"{{{PKG_REL}}}Relationship", Id=rel_id, Type=kind, Target=target)
        parts[name] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    add_rel("ppt/_rels/presentation.xml.rels", "rIdLegAuth", f"{R}/commentAuthors", "commentAuthors.xml")
    add_rel(slide_rels, "rIdLegCm", f"{R}/comments", "../comments/comment1.xml")
    types = etree.fromstring(parts["[Content_Types].xml"])
    for part, kind in (
        ("ppt/commentAuthors.xml", f"{OFFICE}.commentAuthors+xml"),
        ("ppt/comments/comment1.xml", f"{OFFICE}.comments+xml"),
    ):
        etree.SubElement(types, f"{{{CT}}}Override", PartName=f"/{part}", ContentType=kind)
    parts["[Content_Types].xml"] = etree.tostring(types, xml_declaration=True, encoding="UTF-8", standalone=True)
    parts["ppt/commentAuthors.xml"] = (
        f'<p:cmAuthorLst xmlns:p="{P}"><p:cmAuthor id="0" name="Reviewer" initials="RV" lastIdx="1" clrIdx="0"/>'
        "</p:cmAuthorLst>"
    ).encode()
    parts["ppt/comments/comment1.xml"] = (
        f'<p:cmLst xmlns:p="{P}"><p:cm authorId="0" dt="2026-11-17T09:00:00.000" idx="1">'
        f'<p:pos x="10" y="10"/><p:text>{text}</p:text></p:cm></p:cmLst>'
    ).encode()
    with zipfile.ZipFile(deck_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)


@pytest.fixture(autouse=True)
def no_model(monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_a_deck_goes_out_comes_back_with_edits_and_goes_out_again(tmp_path, capsys):
    started = time.monotonic()
    shutil.copyfile(fixture_path("slides", "deck.md"), tmp_path / "deck.md")
    assert main(["build", str(tmp_path / "deck.md")]) == 0
    capsys.readouterr()
    v1 = _send(tmp_path, "deck", "v1", capsys)
    assert (v1 / "deck.pptx").is_file()

    copy = tmp_path / "deck-reviewed.pptx"
    shutil.copyfile(v1 / "deck.pptx", copy)
    deck = Presentation(str(copy))
    for shape in deck.slides[0].shapes:
        if shape.name == "cover/paragraphs[0]":
            runs = [r for p in shape.text_frame.paragraphs for r in p.runs]
            runs[0].text = REVIEWER_WORDS
            for run in runs[1:]:
                run.text = ""
    ids = deck.part._element.find(f"{{{P}}}sldIdLst")
    victim = ids[3]
    deck.part.drop_rel(victim.get(f"{{{R}}}id"))
    ids.remove(victim)
    deck.save(str(copy))
    _legacy_comment(copy, 3, "Say how many readings drop.")

    plan = _read(copy, capsys)
    assert plan["sections"]["cover"]["fields"]["paragraphs[0]"] == REVIEWER_WORDS
    assert [c["section"] for c in plan["confirm"] if c["kind"] == "delete"] == ["closing"]
    assert plan["sections"]["statement"]["confirm"]

    v2 = _apply_and_rebuild(tmp_path, "deck", _decide(plan, ASK), capsys)

    sections = _sections(tmp_path / "deck.md")
    assert sections["statement"].redraft == ASK
    assert "closing" not in sections
    assert sections["cover"].paragraphs == [REVIEWER_WORDS]
    assert REVIEWER_WORDS in _composition_text(v2)
    assert "closing" not in _composition_text(v2)
    assert (v2 / "deck.pptx").is_file()
    assert time.monotonic() - started < 120


def test_a_document_goes_out_comes_back_with_edits_and_goes_out_again(tmp_path, capsys):
    started = time.monotonic()
    (tmp_path / "report.md").write_text(DOC_SOURCE, encoding="utf-8")
    assert main(["build", str(tmp_path / "report.md")]) == 0
    capsys.readouterr()
    v1 = _send(tmp_path, "report", "v1", capsys)

    copy = tmp_path / "report-reviewed.docx"
    shutil.copyfile(v1 / "report.docx", copy)
    document = Document(str(copy))
    for paragraph in document.paragraphs:
        for run in paragraph.runs:
            if "original wording" in run.text:
                run.text = run.text.replace("original wording", REVIEWER_WORDS)
    gamma = next(r for p in document.paragraphs for r in p.runs if "last paragraph" in r.text)
    document.add_comment(gamma, text="Say how many readings drop.", author="Reviewer")
    for paragraph in [p for p in document.paragraphs if "Beta" in p.text]:
        paragraph._element.getparent().remove(paragraph._element)
    document.save(str(copy))

    plan = _read(copy, capsys)
    assert REVIEWER_WORDS in plan["sections"]["alpha01"]["wording"]
    assert [c["section"] for c in plan["confirm"] if c["kind"] == "delete"] == ["beta01"]
    assert plan["sections"]["gamma01"]["confirm"]

    v2 = _apply_and_rebuild(tmp_path, "report", _decide(plan, ASK), capsys)

    sections = _sections(tmp_path / "report.md")
    assert sections["gamma01"].redraft == ASK
    assert "beta01" not in sections
    assert REVIEWER_WORDS in " ".join(sections["alpha01"].paragraphs)
    assert REVIEWER_WORDS in _composition_text(v2)
    assert "Beta holds" not in _composition_text(v2)
    assert (v2 / "report.docx").is_file()
    assert time.monotonic() - started < 120


def test_the_readme_has_install_steps_for_the_plugin():
    text = README.read_text(encoding="utf-8")
    install = re.search(r"^#+ .*install.*$", text, re.IGNORECASE | re.MULTILINE)
    assert install, "no install heading"
    section = text[install.end() :].split("\n## ", 1)[0]
    assert "/plugin" in section
    assert "uv" in section


def test_the_readme_has_a_five_minute_live_test_with_an_empty_folder():
    text = README.read_text(encoding="utf-8")
    heading = re.search(r"^#+ .*five-minute.*$", text, re.IGNORECASE | re.MULTILINE)
    assert heading, "no five-minute heading"
    section = text[heading.end() :].split("\n## ", 1)[0]
    assert "empty folder" in section
    for skill in ("brand", "create", "review"):
        assert skill in section, skill
    assert "Claude Code" in section
