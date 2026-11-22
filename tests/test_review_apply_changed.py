"""`review apply` applies a plan over a working file that changed since the copy's version.

It names each such section as `changed since v<N>: <id> (<parts>)` and each section the plan names
that the working file no longer has as `missing: <id>`; both exit 0.
"""

import json
import re
import zipfile
from pathlib import Path

import pytest

from ai_docs_kit.cli import main
from ai_docs_kit.source.parser import parse

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
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else -1


@pytest.fixture
def work(tmp_path) -> Path:
    folder = tmp_path / "w"
    folder.mkdir()
    (folder / "report.md").write_text(SOURCE, encoding="utf-8")
    assert main(["build", str(folder / "report.md")]) == 0
    version = folder / "report.versions" / "v1"
    empty = folder / "none.json"
    empty.write_text("[]")
    assert main(["look", str(version), "--findings", str(empty)]) == 0
    return folder


def _plan(work: Path, capsys, edits) -> dict:
    source = work / "report.versions" / "v1" / "report.docx"
    target = work / "report-reviewed.docx"
    with zipfile.ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    xml = parts["word/document.xml"].decode("utf-8")
    for old, new in edits:
        assert old in xml, old
        xml = xml.replace(old, new)
    parts["word/document.xml"] = xml.encode("utf-8")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    assert main(["review", "read", str(target)]) == 0
    out = capsys.readouterr().out
    paths = [Path(line.split()[-1]) for line in out.splitlines() if line.strip().endswith(".json")]
    return json.loads(paths[-1].read_text(encoding="utf-8"))


def _apply(work: Path, plan: dict, tmp_path: Path, capsys) -> tuple[int, str, str]:
    decided = tmp_path / "decided.json"
    decided.write_text(json.dumps(plan), encoding="utf-8")
    code = _run(["review", "apply", str(work / "report.md"), "--plan", str(decided)])
    out = capsys.readouterr()
    return code, out.out, out.err


def _sections(work: Path) -> dict:
    doc, _ = parse((work / "report.md").read_text(encoding="utf-8"))
    return {s.id: s for s in doc.sections}


def _edit_work(work: Path, old: str, new: str) -> None:
    path = work / "report.md"
    text = path.read_text(encoding="utf-8")
    assert old in text, old
    path.write_text(text.replace(old, new), encoding="utf-8")


def test_a_title_changed_since_the_version_is_applied_and_named(work, tmp_path, capsys):
    plan = _plan(work, capsys, [("original wording", "revised wording")])
    _edit_work(work, "## Alpha", "## Alpha renamed")
    code, out, err = _apply(work, plan, tmp_path, capsys)
    assert code == 0, err
    assert "revised wording" in " ".join(_sections(work)["alpha01"].paragraphs)
    lines = [line for line in out.splitlines() if line.startswith("changed since")]
    assert len(lines) == 1
    assert re.fullmatch(r"changed since v1: alpha01 \(.*title.*\)", lines[0]), lines[0]


def test_changed_paragraphs_are_applied_named_and_kept_in_the_oplog(work, tmp_path, capsys):
    plan = _plan(work, capsys, [("original wording", "revised wording")])
    _edit_work(work, "original wording", "edited since sending")
    code, out, err = _apply(work, plan, tmp_path, capsys)
    assert code == 0, err
    section = _sections(work)["alpha01"]
    assert "revised wording" in " ".join(section.paragraphs)
    assert "edited since sending" not in " ".join(section.paragraphs)
    lines = [line for line in out.splitlines() if line.startswith("changed since")]
    assert len(lines) == 1
    assert re.fullmatch(r"changed since v1: alpha01 \(.*paragraphs.*\)", lines[0]), lines[0]
    assert "edited since sending" in (work / ".ai_docs_kit" / "oplog.jsonl").read_text(encoding="utf-8")


def test_every_changed_section_gets_its_own_line_and_untouched_ones_none(work, tmp_path, capsys):
    plan = _plan(
        work,
        capsys,
        [("original wording", "revised wording"), ("last paragraph", "closing paragraph")],
    )
    _edit_work(work, "original wording", "edited one")
    _edit_work(work, "a last paragraph", "an edited end")
    _edit_work(work, "second paragraph", "edited paragraph")
    code, out, err = _apply(work, plan, tmp_path, capsys)
    assert code == 0, err
    lines = [line for line in out.splitlines() if line.startswith("changed since")]
    assert sorted(line.split()[3] for line in lines) == ["alpha01", "gamma01"]


def test_a_section_unchanged_since_the_version_prints_no_changed_line(work, tmp_path, capsys):
    plan = _plan(work, capsys, [("original wording", "revised wording")])
    code, out, err = _apply(work, plan, tmp_path, capsys)
    assert code == 0, err
    assert "changed since" not in out and "missing:" not in out


def test_a_section_deleted_since_the_version_is_printed_as_missing(work, tmp_path, capsys):
    plan = _plan(
        work,
        capsys,
        [("original wording", "revised wording"), ("second paragraph", "next paragraph")],
    )
    path = work / "report.md"
    text = path.read_text(encoding="utf-8")
    start = text.index("::: {#beta01")
    end = text.index(":::\n", start) + 4
    path.write_text(text[:start] + text[end:], encoding="utf-8")
    code, out, err = _apply(work, plan, tmp_path, capsys)
    assert code == 0, err
    assert "missing: beta01" in out.splitlines()
    sections = _sections(work)
    assert "beta01" not in sections
    assert "revised wording" in " ".join(sections["alpha01"].paragraphs)
    assert "changed since" not in out


def test_a_malformed_plan_still_exits_2_and_names_the_file(work, tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    code = _run(["review", "apply", str(work / "report.md"), "--plan", str(bad)])
    err = capsys.readouterr().err
    assert code == 2
    assert "bad.json" in err
