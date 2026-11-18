"""A Word comment whose range crosses sections reaches every section it overlaps.

Each copy in `sections[<id>].confirm` carries `spans`, the ids of all the sections the comment
overlaps in document order, so the review skill can show it once.
"""

import json
import shutil
import zipfile
from pathlib import Path

import pytest
from docx import Document

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

::: {#beta01 .section intent="body"}
## Beta

Beta holds the second paragraph of the note.
:::

::: {#gamma01 .section intent="body"}
## Gamma

Gamma closes the note with a last paragraph.
:::
"""

ALL = ["alpha01", "beta01", "gamma01"]


def _run(argv: list[str]) -> int:
    try:
        return main(argv)
    except SystemExit as error:
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
    return folder


@pytest.fixture
def work(sent, tmp_path) -> Path:
    shutil.copytree(sent, tmp_path / "w")
    return tmp_path / "w"


def _plan(work: Path, capsys, first: str, last: str, text: str) -> dict:
    """The plan for a copy with one comment whose range runs from the run holding `first` to the run holding `last`."""
    source = work / "report.versions" / "v1" / "report.docx"
    target = work / "report-reviewed.docx"
    with zipfile.ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    document = Document(str(target))
    runs = [r for p in document.paragraphs for r in p.runs]
    start = next(r for r in runs if first in r.text)
    end = next(r for r in runs if last in r.text)
    document.add_comment(runs=[start, end], text=text, author="Reviewer B")
    document.save(str(target))
    assert main(["review", "read", str(target)]) == 0
    out = capsys.readouterr().out
    paths = [Path(line.split()[-1]) for line in out.splitlines() if line.strip().endswith(".json")]
    return json.loads(paths[-1].read_text(encoding="utf-8"))


def _comments(plan: dict, name: str) -> list[dict]:
    return [i for i in plan["sections"].get(name, {}).get("confirm") or [] if i["kind"] == "comment"]


def test_a_comment_across_three_sections_reaches_each_with_the_same_text_and_author(work, capsys):
    plan = _plan(work, capsys, "original wording", "last paragraph", "Tighten all of this.")
    for name in ALL:
        items = _comments(plan, name)
        assert len(items) == 1, name
        assert items[0]["author"] == "Reviewer B"
        assert "Tighten all of this." in items[0]["text"]


def test_each_copy_carries_the_spans_in_document_order(work, capsys):
    plan = _plan(work, capsys, "original wording", "last paragraph", "Tighten all of this.")
    for name in ALL:
        assert _comments(plan, name)[0]["spans"] == ALL


def test_a_comment_across_two_sections_skips_the_third(work, capsys):
    plan = _plan(work, capsys, "original wording", "second paragraph", "Merge these.")
    assert _comments(plan, "alpha01")[0]["spans"] == ["alpha01", "beta01"]
    assert _comments(plan, "beta01")[0]["spans"] == ["alpha01", "beta01"]
    assert _comments(plan, "gamma01") == []


def test_a_comment_inside_one_section_spans_only_that_section(work, capsys):
    plan = _plan(work, capsys, "second paragraph", "second paragraph", "Say how many.")
    items = _comments(plan, "beta01")
    assert len(items) == 1
    assert items[0]["spans"] == ["beta01"]
    assert _comments(plan, "alpha01") == []
    assert _comments(plan, "gamma01") == []


def test_the_schema_names_spans():
    schema = Path(__file__).resolve().parents[1] / "docs" / "schemas" / "review" / "ReviewPlan.schema.json"
    assert "spans" in schema.read_text(encoding="utf-8")


def test_apply_redrafts_an_accepted_spanning_comment_once_per_section(work, tmp_path, capsys):
    plan = _plan(work, capsys, "original wording", "last paragraph", "Say how many readings drop.")
    for name in ALL:
        _comments(plan, name)[0].update(accepted=True, action="redraft", ask="say how many readings drop")
    decided = tmp_path / "decided.json"
    decided.write_text(json.dumps(plan), encoding="utf-8")
    code = _run(["review", "apply", str(work / "report.md"), "--plan", str(decided)])
    out = capsys.readouterr()
    assert code == 0, out.err
    last = out.out.rstrip("\n").splitlines()[-1]
    touched = json.loads(last[len("touched ") :])
    assert sorted(touched["redrafted"]) == ALL
    text = (work / "report.md").read_text(encoding="utf-8")
    assert text.count('redraft="say how many readings drop"') == 3
