"""Issue 376 review: manual edits and ordinary reasons cannot corrupt history."""

import json

import pytest

from ai_docs_kit import api, cli
from ai_docs_kit.model import Document, Patch, PatchOp, Section
from ai_docs_kit.source.files import apply_to_file
from ai_docs_kit.source.ids import IdStore
from ai_docs_kit.source.patches import PatchRejected
from ai_docs_kit.source.serialiser import serialise


def _working(root, name="note.md"):
    path = root / name
    path.write_text(
        serialise(
            Document(
                front={"format": "doc", "title": "Working note"},
                format="doc",
                sections=[
                    Section(id=key, intent="body", owner="ai", paragraphs=[f"The {key} wording stays."])
                    for key in ("first", "middle", "last")
                ],
            )
        ),
        encoding="utf-8",
    )
    return path


def _snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def _log(path):
    return path.parent / ".ai_docs_kit/oplog.jsonl"


def _redo_refused(path, capsys):
    before = _snapshot(path.parent)
    capsys.readouterr()
    assert cli.main(["redo", str(path)]) == 1
    output = capsys.readouterr()
    assert not output.out
    assert len(output.err.splitlines()) == 1 and "redo" in output.err.lower()
    with pytest.raises(PatchRejected):
        api.redo(path, api.read_document(path).rev)
    assert _snapshot(path.parent) == before, "redo refusal must preserve all file and oplog bytes"


@pytest.mark.parametrize("change", ["same-section", "other-section", "front-matter", "line-endings"])
@pytest.mark.parametrize("other_file_edit", [False, True])
def test_redo_refuses_manual_edits_after_a_clean_round_trip(tmp_path, capsys, change, other_file_edit):
    path = _working(tmp_path)
    api.edit_fields(path, "first", {"paragraphs": ["The edited wording stays."]}, 0)
    edited = path.read_bytes()
    api.undo(path, 1)
    restored = path.read_bytes()
    if other_file_edit:
        other = _working(tmp_path, "other.md")
        api.edit_fields(other, "last", {"paragraphs": ["An independent edit."]}, 2)
    api.redo(path, api.read_document(path).rev)
    assert path.read_bytes() == edited, "an unchanged working file can be redone"
    api.undo(path, api.read_document(path).rev)
    assert path.read_bytes() == restored
    old, new = {
        "same-section": (b"The first wording stays.", "The person's café wording stays.".encode()),
        "other-section": (b"The middle wording stays.", b"The separate manual wording stays."),
        "front-matter": (b"Working note", b"Manually retitled note"),
        "line-endings": (b"\n", b"\r\n"),
    }[change]
    assert old in restored
    path.write_bytes(restored.replace(old, new))
    if other_file_edit:
        api.edit_fields(other, "last", {"paragraphs": ["Another independent edit."]}, api.read_document(path).rev)
    _redo_refused(path, capsys)
    _redo_refused(path, capsys)


def test_manual_edit_discards_the_old_redo_branch_across_later_history_steps(tmp_path, capsys):
    path = _working(tmp_path)
    api.edit_fields(path, "first", {"paragraphs": ["The first edited wording."]}, 0)
    api.edit_fields(path, "middle", {"paragraphs": ["The middle edited wording."]}, 1)
    api.undo(path, 2)
    api.redo(path, 3)
    api.undo(path, 4)
    path.write_bytes(path.read_bytes().replace(b"The last wording stays.", b"The manual wording stays."))
    manual = path.read_bytes()
    history = _log(path).read_bytes()
    assert api.undo(path, 5).target_rev == 1
    assert b"The manual wording stays." in path.read_bytes()
    assert api.redo(path, 6).target_rev == 1
    assert path.read_bytes() == manual
    assert _log(path).read_bytes().startswith(history), "discarding redo must not rewrite the oplog"
    _redo_refused(path, capsys)


@pytest.mark.parametrize("author", ["ai", "human", "system"])
@pytest.mark.parametrize("reason", ["undo rev 1", "redo rev 1", "undo rev 999"])
@pytest.mark.parametrize("earlier_patch", [False, True])
def test_ordinary_patch_reasons_never_identify_history_actions(tmp_path, capsys, author, reason, earlier_patch):
    path = _working(tmp_path)
    ids = IdStore(tmp_path / ".ai_docs_kit/ids.json")

    def edit(base_rev, reason):
        apply_to_file(
            path,
            Patch(
                base_rev=base_rev,
                author=author,
                reason=reason,
                ops=[PatchOp(op="set_fields", section_id="first", fields={"paragraphs": [reason]})],
            ),
            _log(path),
            ids,
        )

    revision = int(earlier_patch)
    if earlier_patch:
        edit(0, "ordinary wording")
    before = path.read_bytes()
    edit(revision, reason)
    edited = path.read_bytes()
    original_log = _log(path).read_bytes()
    capsys.readouterr()
    assert cli.main(["undo", str(path)]) == 0
    assert path.read_bytes() == before
    assert cli.main(["redo", str(path)]) == 0
    assert path.read_bytes() == edited
    assert not capsys.readouterr().err
    assert _log(path).read_bytes().startswith(original_log)
    entries = [json.loads(line) for line in _log(path).read_text().splitlines()]
    original, undo, redo = entries[-3:]
    assert original["reason"] == reason
    assert not original.get("history")
    assert undo["history"] == {"action": "undo", "target_rev": revision + 1}
    assert redo["history"] == {"action": "redo", "target_rev": revision + 1}
    assert undo["ops"] == original["inverse"] and redo["ops"] == original["ops"]
