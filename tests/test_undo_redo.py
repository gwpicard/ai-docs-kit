"""Issue 376: undo and redo replay recorded operations through public entry points.

Oracles: the issue's CLI checking recipe, ENGINE.md section 13.8, the oplog
written by source/files.py and inverse_ops in source/patches.py. Fixtures use
canonical Markdown because patches already serialise the whole working file.
Result model names and empty-history error codes are deliberately left open.
"""

import fcntl
import inspect
import json
import os
import re
from pathlib import Path
from typing import Any, get_type_hints

import pytest
from pydantic import BaseModel, TypeAdapter

from ai_docs_kit import api, cli
from ai_docs_kit.model import Section
from ai_docs_kit.source import files
from ai_docs_kit.source.patches import PatchRejected
from ai_docs_kit.source.serialiser import serialise


def _working(root, format_="doc", reverse=False, name="working note.md"):
    root.mkdir(parents=True, exist_ok=True)
    intent = "body" if format_ == "doc" else "statement"
    blocks = [
        f'::: {{#{key} .section intent="{intent}" owner="ai"}}\n## {title}\n\n{words}\n:::\n'
        for key, title, words in (
            ("first", "Summary", "The agreed wording stays."),
            ("middle", "Context", "The separate wording stays."),
            ("last", "Conclusion", "The final wording stays."),
        )
    ]
    if reverse:
        blocks.reverse()
    path = root / name
    path.write_text(
        f"---\ndoctype: report\nformat: {format_}\ntitle: Working note\n---\n\n"
        "## Sources\n\n- [S1] the reading was 12.\n\n" + "\n".join(blocks),
        encoding="utf-8",
    )
    assert serialise(api.read_document(path)).encode() == path.read_bytes(), "use canonical fixture bytes"
    return path


def _run(capsys, *args):
    capsys.readouterr()
    try:
        code = cli.main([str(arg) for arg in args])
    except SystemExit as error:
        code = error.code
    output = capsys.readouterr()
    return code, output.out, output.err


def _put(capsys, path, section_id="first", words="The reading was 12. [S1]"):
    section = next(section for section in api.read_document(path).sections if section.id == section_id)
    block = path.parent / "replacement.md"
    block.write_text(
        f'::: {{#{section_id} .section intent="{section.intent}"}}\n## {section.title}\n\n{words}\n:::\n',
        encoding="utf-8",
    )
    code, out, err = _run(capsys, "section", "put", path, section_id, "--from", block)
    assert code == 0, (out, err)
    return path.read_bytes()


def _log(path):
    return path.parent / ".ai_docs_kit" / "oplog.jsonl"


def _entries(path):
    return [json.loads(line) for line in _log(path).read_bytes().splitlines() if line.strip()]


def _snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def _step(capsys, command, path, target_rev):
    history = _log(path).read_bytes()
    entries = _entries(path)
    revision = len(entries) + 1
    code, out, err = _run(capsys, command, path)
    assert code == 0, f"{command} must apply a patch: {(out, err)}"
    assert not err
    assert re.search(rf"\b{revision}\b", out), f"print the new revision {revision}: {out!r}"
    assert _log(path).read_bytes().startswith(history), "history must stay byte-for-byte append-only"
    after = _entries(path)
    assert len(after) == revision, "append exactly one patch per undo or redo"
    entry = after[-1]
    assert entry["rev"] == revision and entry["file"] == path.name
    assert entry["author"] == "human"
    assert entry["reason"] == f"{command} rev {target_rev}"
    assert entry["inverse"] is not None, "undo and redo must themselves record an inverse"
    target = next(item for item in entries if item["rev"] == target_rev)
    assert entry["ops"] == target["inverse" if command == "undo" else "ops"]
    assert api.read_document(path).rev == revision


def _refused(capsys, command, path):
    before = _snapshot(path.parent)
    code, out, err = _run(capsys, command, path)
    assert code == 1, f"{command} must refuse with exit 1: {(out, err)}"
    assert not out
    assert len(err.splitlines()) == 1 and err.strip(), "print one useful stderr line"
    assert "traceback" not in err.lower()
    assert _snapshot(path.parent) == before, "refusal must not change working files or history"
    return err.lower()


@pytest.mark.parametrize(("format_", "reverse"), [("doc", False), ("slides", True)])
@pytest.mark.parametrize("later_edit", [False, True], ids=["exact-restoration", "keep-unrelated-edit"])
def test_section_put_undo_redo_restores_bytes_and_preserves_later_unrelated_wording(
    tmp_path, capsys, format_, reverse, later_edit
):
    path = _working(tmp_path, format_, reverse)
    before = path.read_bytes()
    after = _put(capsys, path)
    assert before != after
    original_owner = next(s.owner for s in api.read_document(path).sections if s.id == "first")
    if later_edit:
        # A person can edit the working file directly after the logged patch.
        # Replaying its section inverse must preserve this unrelated section.
        old = b"The separate wording stays."
        new = "The separate café wording now stays.".encode()
        assert old in before and old in after
        before, after = before.replace(old, new), after.replace(old, new)
        path.write_bytes(after)
    _step(capsys, "undo", path, 1)
    assert path.read_bytes() == before, "undo must restore the put without dropping a later unrelated edit"
    assert next(s.owner for s in api.read_document(path).sections if s.id == "first") == original_owner
    _step(capsys, "redo", path, 1)
    assert path.read_bytes() == after


@pytest.mark.parametrize("reverse", [False, True])
def test_three_puts_walk_back_and_forward_skipping_history_commands(tmp_path, capsys, reverse):
    path = _working(tmp_path, reverse=reverse)
    states = [path.read_bytes()]
    # Two writes to the same section distinguish a stack from a section scan.
    for section_id, words in (
        ("first", "The reading was 12. [S1]"),
        ("middle", "The reading was 12. [S1]"),
        ("first", "The agreed wording stays."),
    ):
        states.append(_put(capsys, path, section_id, words))
    for target in (3, 2, 1):
        _step(capsys, "undo", path, target)
        assert path.read_bytes() == states[target - 1]
    assert "undo" in _refused(capsys, "undo", path)
    for target in (1, 2, 3):
        _step(capsys, "redo", path, target)
        assert path.read_bytes() == states[target]
    assert "redo" in _refused(capsys, "redo", path)
    _step(capsys, "undo", path, 3)
    assert path.read_bytes() == states[2], "a redo entry must not become a new ordinary edit"


@pytest.mark.parametrize("command", ["undo", "redo"])
def test_empty_history_refuses_on_one_stderr_line(tmp_path, capsys, command):
    path = _working(tmp_path)
    assert command in _refused(capsys, command, path)


@pytest.mark.parametrize("edit_kind", ["section-put", "public-api"])
def test_other_edit_after_undo_clears_redo_history(tmp_path, capsys, edit_kind):
    path = _working(tmp_path)
    _put(capsys, path)
    _step(capsys, "undo", path, 1)
    if edit_kind == "section-put":
        _put(capsys, path, "middle")
    else:
        api.edit_fields(path, "middle", {"paragraphs": ["A person's later wording."]}, base_rev=2)
    assert "redo" in _refused(capsys, "redo", path)
    _step(capsys, "undo", path, 3)
    assert "redo" not in _entries(path)[-1]["reason"]
    _step(capsys, "redo", path, 3)
    assert "redo" in _refused(capsys, "redo", path), "the discarded branch must not reappear"


@pytest.mark.parametrize("reverse", [False, True])
def test_null_inverse_stops_the_walk_without_skipping_to_an_older_patch(tmp_path, capsys, reverse):
    path = _working(tmp_path, reverse=reverse)
    _put(capsys, path)
    # A real move patch currently records no inverse. Do not fabricate history.
    api.move_section(path, "first", "last", base_rev=1)
    assert _entries(path)[1]["inverse"] is None
    barrier_state = path.read_bytes()
    _put(capsys, path, "middle")
    _step(capsys, "undo", path, 3)
    assert path.read_bytes() == barrier_state
    message = _refused(capsys, "undo", path)
    assert re.search(r"\b2\b", message), "identify the revision blocking the walk"
    assert "inverse" in message or "cannot undo" in message or "not undoable" in message
    _step(capsys, "redo", path, 3)


@pytest.mark.parametrize("reverse", [False, True])
def test_shared_oplog_undo_targets_only_the_named_working_file(tmp_path, capsys, reverse):
    first = _working(tmp_path, reverse=reverse)
    second = _working(tmp_path, reverse=not reverse, name="other note.md")
    initial = first.read_bytes()
    changed = _put(capsys, first)
    other_changed = _put(capsys, second, "middle")
    _step(capsys, "undo", first, 1)
    assert first.read_bytes() == initial
    assert second.read_bytes() == other_changed, "undo must not drop a later edit to another working file"
    _step(capsys, "redo", first, 1)
    assert first.read_bytes() == changed and second.read_bytes() == other_changed


def _function(name):
    function = getattr(api, name, None)
    assert callable(function), f"ai_docs_kit.api must offer {name}(path, base_rev)"
    return function


def _call(name, path, base_rev):
    function = _function(name)
    hints = get_type_hints(function)
    assert {"path", "base_rev", "return"} <= hints.keys(), f"type {name}'s inputs and result"
    assert all(hints[key] is not Any for key in ("path", "base_rev", "return"))
    assert {"path", "base_rev"} <= inspect.signature(function).parameters.keys()
    result = function(path=path, base_rev=base_rev)
    assert isinstance(result, BaseModel), "return a typed model, following the existing public edit API"
    assert TypeAdapter(hints["return"]).validate_python(result) == result
    assert result.rev == base_rev + 1
    return result


@pytest.mark.parametrize("operation", ["fields", "add", "delete-first", "delete-middle", "delete-last"])
def test_typed_public_api_undo_redo_restores_content_order_and_ownership(tmp_path, capsys, operation):
    _function("undo")
    _function("redo")
    path = _working(tmp_path)
    before = path.read_bytes()
    if operation == "fields":
        api.edit_fields(path, "first", {"paragraphs": ["The person's café wording."], "note": "Keep this."}, 0)
        assert api.read_document(path).sections[0].owner == "human"
    elif operation == "add":
        api.add_section(path, None, Section(intent="body", paragraphs=["The added wording."]), 0)
    else:
        api.delete_section(path, operation.removeprefix("delete-"), 0)
    after = path.read_bytes()
    assert before != after
    history = _log(path).read_bytes()
    _call("undo", str(path), 1)
    assert path.read_bytes() == before
    assert _log(path).read_bytes().startswith(history)
    assert _entries(path)[-1]["reason"] == "undo rev 1"
    _call("redo", path, 2)
    assert path.read_bytes() == after
    entries = _entries(path)
    assert len(entries) == 3 and entries[-1]["reason"] == "redo rev 1"
    assert [entry["author"] for entry in entries[1:]] == ["human", "human"]
    assert entries[1]["ops"] == entries[0]["inverse"]
    assert entries[2]["ops"] == entries[0]["ops"]


@pytest.mark.parametrize("command", ["undo", "redo"])
def test_public_history_commands_reject_stale_revision_without_consuming_history(tmp_path, capsys, command):
    function = _function(command)
    _function("undo")
    path = _working(tmp_path)
    _put(capsys, path)
    revision = 1
    if command == "redo":
        _call("undo", path, revision)
        revision += 1
    before = _snapshot(tmp_path)
    with pytest.raises(PatchRejected) as caught:
        function(path, base_rev=revision - 1)
    assert caught.value.code == "stale-base-rev"
    assert f"rev {revision}" in caught.value.message
    assert _snapshot(tmp_path) == before
    _call(command, path, revision)
    assert len(_entries(path)) == revision + 1


def test_public_undo_and_redo_write_through_the_locked_patch_path(tmp_path, capsys, monkeypatch):
    _function("undo")
    _function("redo")
    path = _working(tmp_path)
    _put(capsys, path)
    writes = []
    write_atomic = files._write_atomic
    open_path = Path.open

    def assert_locked():
        descriptor = os.open(_log(path).parent, os.O_RDONLY)
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(descriptor)

    def observed_open(target, *args, **kwargs):
        if target in (path, _log(path)):
            assert_locked()
        return open_path(target, *args, **kwargs)

    def observed_write(target, text):
        assert_locked()
        writes.append(target)
        return write_atomic(target, text)

    monkeypatch.setattr(Path, "open", observed_open)
    monkeypatch.setattr(files, "_write_atomic", observed_write)
    _call("undo", path, 1)
    _call("redo", path, 2)
    assert writes == [path, path], "each history command must use the existing locked patch writer"
