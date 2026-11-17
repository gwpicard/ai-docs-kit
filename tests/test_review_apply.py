"""`review apply`: a decided review plan lands in the working file.

Decided plan shape these tests pin (recorded under Deviations in PLAN.md): the plan `review read`
wrote, where the person's decisions are added to it. A comment item in `sections[<id>].confirm`
gains `accepted` (bool), `action` (`apply`, `redraft` or `skip`) and, for `apply`, `proposal` (the
section's new wording) or, for `redraft`, `ask`. An item in the top-level `confirm` list gains
`accepted` and `action: "restructure"`. A section's `wording` is applied as it stands.
"""

import json
import shutil
import zipfile
from pathlib import Path

import pytest

from ai_docs_kit.cli import main
from ai_docs_kit.source.parser import parse
from ai_docs_kit.source.serialiser import _section

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

LAST_KEYS = ["applied", "redrafted", "moved", "deleted"]


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
    assert main(["sent", str(version), "--to", "Reviewer"]) == 0
    return folder


@pytest.fixture
def work(sent, tmp_path) -> Path:
    shutil.copytree(sent, tmp_path / "w")
    return tmp_path / "w"


def _review_plan(work: Path, capsys, edits=(), comments=()) -> dict:
    """The plan `review read` writes for a copy of the sent Word file with the given edits and comments."""
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
    if comments:
        from docx import Document

        document = Document(str(target))
        for needle, author, text in comments:
            run = next(r for p in document.paragraphs for r in p.runs if needle in r.text)
            document.add_comment(run, text=text, author=author)
        document.save(str(target))
    assert main(["review", "read", str(target)]) == 0
    out = capsys.readouterr().out
    paths = [Path(line.split()[-1]) for line in out.splitlines() if line.strip().endswith(".json")]
    return json.loads(paths[-1].read_text(encoding="utf-8"))


def _decide(tmp_path: Path, plan: dict) -> Path:
    path = tmp_path / "decided.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    return path


def _apply(work: Path, decided: Path, capsys) -> tuple[int, str, str]:
    code = _run(["review", "apply", str(work / "report.md"), "--plan", str(decided)])
    out = capsys.readouterr()
    return code, out.out, out.err


def _sections(work: Path) -> dict:
    doc, _ = parse((work / "report.md").read_text(encoding="utf-8"))
    return {s.id: s for s in doc.sections}


def _order(work: Path) -> list[str]:
    doc, _ = parse((work / "report.md").read_text(encoding="utf-8"))
    return [s.id for s in doc.sections]


def _touched(out: str) -> dict:
    last = out.rstrip("\n").splitlines()[-1]
    assert last.startswith("touched "), last
    return json.loads(last[len("touched ") :])


def _wording_plan(work: Path, capsys) -> dict:
    return _review_plan(work, capsys, edits=[("original wording", "revised wording")])


def test_wording_is_applied_to_its_section_and_marked_human(work, tmp_path, capsys):
    plan = _wording_plan(work, capsys)
    code, out, err = _apply(work, _decide(tmp_path, plan), capsys)
    assert code == 0, err
    sections = _sections(work)
    assert "Alpha keeps its revised wording here." in _section(sections["alpha01"])
    assert "original wording" not in _section(sections["alpha01"])
    assert sections["alpha01"].owner == "human"
    assert sections["beta01"].owner is None
    assert "Beta holds the second paragraph of the note." in _section(sections["beta01"])
    assert _touched(out) == {"applied": ["alpha01"], "redrafted": [], "moved": [], "deleted": []}


def test_the_last_line_is_touched_with_the_four_lists(work, tmp_path, capsys):
    plan = _wording_plan(work, capsys)
    code, out, _ = _apply(work, _decide(tmp_path, plan), capsys)
    assert code == 0
    touched = _touched(out)
    assert list(touched) == LAST_KEYS
    assert all(isinstance(v, list) for v in touched.values())


def test_a_plan_with_no_decisions_touches_nothing(work, tmp_path, capsys):
    plan = _review_plan(work, capsys)
    before = (work / "report.md").read_bytes()
    code, out, err = _apply(work, _decide(tmp_path, plan), capsys)
    assert code == 0, err
    assert (work / "report.md").read_bytes() == before
    assert _touched(out) == {"applied": [], "redrafted": [], "moved": [], "deleted": []}


def test_an_accepted_redraft_comment_writes_the_ask_and_stays_agent_owned(work, tmp_path, capsys):
    plan = _review_plan(work, capsys, comments=[("second paragraph", "Reviewer B", "Say how many readings drop.")])
    item = plan["sections"]["beta01"]["confirm"][0]
    item.update(accepted=True, action="redraft", ask="say how many readings drop")
    code, out, err = _apply(work, _decide(tmp_path, plan), capsys)
    assert code == 0, err
    beta = _sections(work)["beta01"]
    assert beta.redraft == "say how many readings drop"
    assert beta.owner != "human"
    assert "Beta holds the second paragraph of the note." in _section(beta)
    assert _touched(out) == {"applied": [], "redrafted": ["beta01"], "moved": [], "deleted": []}


def test_an_unaccepted_comment_changes_nothing(work, tmp_path, capsys):
    plan = _review_plan(work, capsys, comments=[("second paragraph", "Reviewer B", "Say how many.")])
    item = plan["sections"]["beta01"]["confirm"][0]
    item.update(accepted=False, action="redraft", ask="say how many")
    before = (work / "report.md").read_bytes()
    code, out, err = _apply(work, _decide(tmp_path, plan), capsys)
    assert code == 0, err
    assert (work / "report.md").read_bytes() == before
    assert _touched(out)["redrafted"] == []


def test_an_accepted_apply_comment_puts_the_proposed_words_in_as_human_owned(work, tmp_path, capsys):
    plan = _review_plan(work, capsys, comments=[("second paragraph", "Reviewer B", "Use: Beta now holds a count.")])
    item = plan["sections"]["beta01"]["confirm"][0]
    item.update(accepted=True, action="apply", proposal="Beta now holds a count of readings.")
    code, out, err = _apply(work, _decide(tmp_path, plan), capsys)
    assert code == 0, err
    beta = _sections(work)["beta01"]
    assert beta.owner == "human"
    assert "Beta now holds a count of readings." in _section(beta)
    assert "second paragraph of the note" not in _section(beta)
    assert _touched(out) == {"applied": ["beta01"], "redrafted": [], "moved": [], "deleted": []}


def test_wording_and_a_redraft_on_different_sections_are_both_applied(work, tmp_path, capsys):
    plan = _review_plan(
        work,
        capsys,
        edits=[("original wording", "revised wording")],
        comments=[("last paragraph", "Reviewer B", "Shorter please.")],
    )
    plan["sections"]["gamma01"]["confirm"][0].update(accepted=True, action="redraft", ask="shorten it")
    code, out, err = _apply(work, _decide(tmp_path, plan), capsys)
    assert code == 0, err
    sections = _sections(work)
    assert sections["alpha01"].owner == "human"
    assert sections["gamma01"].redraft == "shorten it"
    assert _touched(out) == {"applied": ["alpha01"], "redrafted": ["gamma01"], "moved": [], "deleted": []}


def _delete_plan(work: Path, capsys, accepted: bool) -> dict:
    plan = _wording_plan(work, capsys)
    plan["confirm"] = [
        {
            "kind": "delete",
            "section": "beta01",
            "text": "Beta holds the second paragraph of the note.",
            "action": "restructure",
            "accepted": accepted,
        }
    ]
    return plan


def test_an_accepted_delete_removes_the_section(work, tmp_path, capsys):
    code, out, err = _apply(work, _decide(tmp_path, _delete_plan(work, capsys, True)), capsys)
    assert code == 0, err
    assert _order(work) == ["alpha01", "gamma01"]
    touched = _touched(out)
    assert touched["deleted"] == ["beta01"]
    assert touched["applied"] == ["alpha01"]


def test_an_unaccepted_delete_leaves_the_section(work, tmp_path, capsys):
    code, out, err = _apply(work, _decide(tmp_path, _delete_plan(work, capsys, False)), capsys)
    assert code == 0, err
    assert _order(work) == ["alpha01", "beta01", "gamma01"]
    assert _touched(out)["deleted"] == []


@pytest.mark.parametrize("accepted", [True, False])
def test_a_reorder_applies_only_when_accepted(work, tmp_path, capsys, accepted):
    plan = _review_plan(work, capsys)
    plan["confirm"] = [
        {
            "kind": "reorder",
            "text": "The sections now run in this order: alpha01, gamma01, beta01",
            "order": ["alpha01", "gamma01", "beta01"],
            "action": "restructure",
            "accepted": accepted,
        }
    ]
    code, out, err = _apply(work, _decide(tmp_path, plan), capsys)
    assert code == 0, err
    moved = _touched(out)["moved"]
    if accepted:
        assert _order(work) == ["alpha01", "gamma01", "beta01"]
        assert moved and set(moved) <= {"beta01", "gamma01"}
    else:
        assert _order(work) == ["alpha01", "beta01", "gamma01"]
        assert moved == []


def test_a_change_since_the_sent_version_in_a_touched_section_is_refused(work, tmp_path, capsys):
    plan = _wording_plan(work, capsys)
    path = work / "report.md"
    path.write_text(path.read_text().replace("original wording", "edited since sending"), encoding="utf-8")
    before = path.read_bytes()
    code, out, err = _apply(work, _decide(tmp_path, plan), capsys)
    assert code == 1
    assert "alpha01" in err
    assert "beta01" not in err and "gamma01" not in err
    assert path.read_bytes() == before
    assert "touched" not in out


def test_every_changed_touched_section_is_named(work, tmp_path, capsys):
    plan = _review_plan(
        work,
        capsys,
        edits=[("original wording", "revised wording")],
        comments=[("last paragraph", "Reviewer B", "Shorter please.")],
    )
    plan["sections"]["gamma01"]["confirm"][0].update(accepted=True, action="redraft", ask="shorten it")
    path = work / "report.md"
    text = path.read_text().replace("original wording", "edited one").replace("a last paragraph", "an edited end")
    path.write_text(text, encoding="utf-8")
    code, _, err = _apply(work, _decide(tmp_path, plan), capsys)
    assert code == 1
    assert "alpha01" in err and "gamma01" in err


def test_a_change_in_a_section_the_plan_does_not_touch_does_not_block(work, tmp_path, capsys):
    plan = _wording_plan(work, capsys)
    path = work / "report.md"
    path.write_text(path.read_text().replace("second paragraph", "edited paragraph"), encoding="utf-8")
    code, out, err = _apply(work, _decide(tmp_path, plan), capsys)
    assert code == 0, err
    sections = _sections(work)
    assert "edited paragraph" in _section(sections["beta01"])
    assert sections["alpha01"].owner == "human"


def test_a_rebuild_after_apply_keeps_the_human_owned_words(work, tmp_path, capsys):
    plan = _review_plan(
        work,
        capsys,
        edits=[("original wording", "revised wording")],
        comments=[("second paragraph", "Reviewer B", "Use: Beta now holds a count.")],
    )
    plan["sections"]["beta01"]["confirm"][0].update(
        accepted=True, action="apply", proposal="Beta now holds a count of readings."
    )
    code, _, err = _apply(work, _decide(tmp_path, plan), capsys)
    assert code == 0, err
    assert main(["build", str(work / "report.md")]) == 0
    capsys.readouterr()
    sections = _sections(work)
    assert sections["alpha01"].owner == "human" and sections["beta01"].owner == "human"
    assert "Alpha keeps its revised wording here." in _section(sections["alpha01"])
    assert "Beta now holds a count of readings." in _section(sections["beta01"])
    composition = json.loads((work / "report.versions" / "v2" / "composition.json").read_text(encoding="utf-8"))
    words = json.dumps(composition)
    assert "Alpha keeps its revised wording here." in words
    assert "Beta now holds a count of readings." in words


def test_a_missing_plan_exits_2(work, tmp_path, capsys):
    code, _, err = _apply(work, tmp_path / "absent.json", capsys)
    assert code == 2
    assert "absent.json" in err
