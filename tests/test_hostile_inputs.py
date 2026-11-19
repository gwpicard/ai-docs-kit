"""Every command that reads a file meets bad input with exit 2 and one line naming the file, never a traceback.

Five commands (`look --findings`, `look --pages`, `review read`, `review apply`, `rule test`) each get five
kinds of bad file: missing, empty, truncated, the wrong type, and a missing required key or part.
"""

import json
import shutil
import zipfile
from pathlib import Path

import pytest
import yaml

from ai_docs_kit.brand.intake import take_in
from ai_docs_kit.cli import main

SOURCE = """---
doctype: report
format: doc
title: Note
---

::: {#alpha01 .section intent="body"}
## Alpha

Alpha keeps its original wording here.
:::
"""

RULE = {
    "id": "feedback.asap",
    "title": "No ASAP",
    "origin": "feedback",
    "strength": "soft",
    "status": "proposed",
    "severity": "error",
    "tier": "source",
    "check": {"kind": "text-pattern", "field": "paragraphs", "regex": "original"},
    "remedy": {"class": "redraft", "hint": "Give a date instead."},
    "provenance": {"label": "answered", "source": {"comment": "No."}, "by": "Dana"},
}

CASES = ["missing", "empty", "truncated", "wrong-type", "missing-key"]


def _run(argv: list[str]) -> int:
    try:
        return main(argv)
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else -1


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    folder = tmp_path_factory.mktemp("built")
    (folder / "report.md").write_text(SOURCE, encoding="utf-8")
    assert main(["build", str(folder / "report.md")]) == 0
    empty = folder / "none.json"
    empty.write_text("[]")
    assert main(["look", str(folder / "report.versions" / "v1"), "--findings", str(empty)]) == 0
    return folder


@pytest.fixture
def work(built, tmp_path) -> Path:
    shutil.copytree(built, tmp_path / "w")
    return tmp_path / "w"


def _json_file(path: Path, case: str, good, wrong, missing_key) -> Path:
    """Write the bad file for `case` from a valid `good`, a `wrong`-typed and a `missing_key` content."""
    if case == "empty":
        path.write_text("")
    elif case == "truncated":
        path.write_text(json.dumps(good)[:-3])
    elif case == "wrong-type":
        path.write_text(json.dumps(wrong))
    elif case == "missing-key":
        path.write_text(json.dumps(missing_key))
    return path


def _check(code: int, capsys, path: Path) -> None:
    err = capsys.readouterr().err
    assert code == 2, err
    assert "Traceback" not in err
    lines = [line for line in err.splitlines() if line.strip()]
    assert len(lines) == 1, err
    assert path.name in lines[0], err


@pytest.mark.parametrize("case", CASES)
def test_look_findings(work, capsys, case):
    version = work / "report.versions" / "v1"
    path = work / "agent.json"
    good = [{"page": 1, "section": "alpha01", "severity": "warn", "rule": "x", "message": "m"}]
    _json_file(path, case, good, {"page": 1}, [{"page": 1}])
    _check(_run(["look", str(version), "--findings", str(path)]), capsys, path)


@pytest.mark.parametrize("case", CASES)
def test_look_pages(work, capsys, case):
    version = work / "report.versions" / "v1"
    path = version / "pages" / "pages.json"
    if case == "missing":
        path.unlink()
    else:
        good = [{"page": 1, "sections": ["alpha01"]}]
        _json_file(path, case, good, {"pages": 3}, [{"page": 1}])
    _check(_run(["look", str(version), "--pages"]), capsys, path)


@pytest.mark.parametrize("case", CASES)
def test_review_read(work, capsys, case):
    source = work / "report.versions" / "v1" / "report.docx"
    path = work / "report-reviewed.docx"
    if case == "empty":
        path.write_bytes(b"")
    elif case == "truncated":
        data = source.read_bytes()
        path.write_bytes(data[: len(data) // 2])
    elif case == "wrong-type":
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("notes.txt", "not an office file")
    elif case == "missing-key":
        with zipfile.ZipFile(source) as old, zipfile.ZipFile(path, "w") as archive:
            for name in old.namelist():
                if name != "word/document.xml":
                    archive.writestr(name, old.read(name))
    _check(_run(["review", "read", str(path)]), capsys, path)


@pytest.mark.parametrize("case", CASES)
def test_review_apply(work, capsys, case):
    path = work / "plan.json"
    good = {"sections": {"alpha01": {"confirm": []}}, "confirm": []}
    _json_file(path, case, good, ["not", "a", "plan"], {"confirm": []})
    _check(_run(["review", "apply", str(work / "report.md"), "--plan", str(path)]), capsys, path)


@pytest.mark.parametrize("case", CASES)
def test_rule_test(work, capsys, case):
    path = work / "rule.yaml"
    if case == "empty":
        path.write_text("")
    elif case == "truncated":
        path.write_text(yaml.safe_dump(RULE)[:-1] + "\n  : [unclosed")
    elif case == "wrong-type":
        path.write_text(yaml.safe_dump(["not", "a", "rule"]))
    elif case == "missing-key":
        path.write_text(yaml.safe_dump({k: v for k, v in RULE.items() if k != "check"}))
    example = f"{work / 'report.versions' / 'v1'}/alpha01"
    _check(_run(["rule", "test", str(path), "--example", example]), capsys, path)


def _brand(tmp_path: Path) -> Path:
    brand = tmp_path / "acme"
    (brand / "materials" / "notes").mkdir(parents=True)
    (brand / "materials" / "notes" / "a.txt").write_text("first")
    (brand / "materials" / "notes" / "b.txt").write_text("second")
    return brand


def test_intake_lists_a_vanished_file_as_unread_and_continues(tmp_path, monkeypatch):
    brand = _brand(tmp_path)
    real = Path.read_bytes

    def vanishing(self: Path) -> bytes:
        if self.name == "a.txt":
            self.unlink()
        return real(self)

    monkeypatch.setattr(Path, "read_bytes", vanishing)
    manifest = take_in(brand)
    entries = {Path(f.path).name: f for f in manifest.files}
    assert entries["a.txt"].unread
    assert entries["b.txt"].unread is None
    assert entries["b.txt"].sha256
