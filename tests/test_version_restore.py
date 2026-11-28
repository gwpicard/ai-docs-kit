"""Issue 392: saved working files restore as one reversible, append-only patch.

Oracles: the issue's CLI recipe and owner decision, the immutable versions in
tests/judge/test_m4_07_versions.py, and ENGINE.md sections 5.6 and 13.8.
Real builds supply readable controls; changed wording, membership and order
seed defects that a source overwrite or a history reset cannot safely repair.
The public API follows the existing typed edit-result convention without
prescribing a new result model name or a particular section diff algorithm.
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


def _working(root, format_="doc", reverse=False):
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
    path = root / "working note.md"
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


def _build(capsys, path, number):
    code, out, err = _run(capsys, "build", path)
    assert code == 0, f"the readable control must build: {(out, err)}"
    version = path.with_suffix(".versions") / f"v{number}"
    assert Path(out.strip().splitlines()[-1]) == version
    assert (version / "manifest.json").is_file()
    return version


def _put(capsys, path, words):
    section = next(section for section in api.read_document(path).sections if section.id == "first")
    replacement = path.parent / "replacement.md"
    replacement.write_text(
        f'::: {{#first .section intent="{section.intent}"}}\n## Summary\n\n{words}\n:::\n',
        encoding="utf-8",
    )
    code, out, err = _run(capsys, "section", "put", path, "first", "--from", replacement)
    assert code == 0, (out, err)


def _log(path):
    return path.parent / ".ai_docs_kit" / "oplog.jsonl"


def _entries(path):
    return [json.loads(line) for line in _log(path).read_bytes().splitlines() if line.strip()]


def _snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def _pair(capsys, root, format_="doc", reverse=False, restructure=False, *, raw_layout=False):
    path = _working(root, format_, reverse)
    if raw_layout:
        # Copy original bytes rather than rebuilding Markdown from parsed fields.
        path.write_bytes(path.read_bytes().replace(b'owner="ai"', b"owner=ai").replace(b"\n", b"\r\n"))
    v1 = _build(capsys, path, 1)
    first = path.read_bytes()
    immutable = _snapshot(v1)
    _put(capsys, path, "The reading was 12. [S1]")
    _put(capsys, path, "The reading is 12. [S1]")
    assert len(_entries(path)) == 2, "seed real history after v1"
    if restructure:
        # A person also changes section membership and order in the working file.
        doc = api.read_document(path)
        remaining = [section for section in doc.sections if section.id != "middle"]
        added = Section(
            id="added",
            intent="body" if format_ == "doc" else "statement",
            title="Added wording",
            paragraphs=["The later café wording stays."],
            owner="human",
        )
        doc.sections = [added, *reversed(remaining)]
        path.write_text(serialise(doc), encoding="utf-8")
    v2 = _build(capsys, path, 2)
    second = path.read_bytes()
    assert first != second
    assert _snapshot(v1) == immutable, "building v2 must preserve every v1 file"
    return path, v1, v2, first, second


@pytest.mark.parametrize(("format_", "reverse"), [("doc", False), ("slides", True)])
def test_every_version_keeps_its_exact_source_without_changing_manifest_outputs(tmp_path, capsys, format_, reverse):
    path, v1, v2, first, second = _pair(capsys, tmp_path, format_, reverse, raw_layout=True)
    expected_outputs = [f"{path.stem}.pdf", f"{path.stem}.{'docx' if format_ == 'doc' else 'pptx'}"]
    for version, source in ((v1, first), (v2, second)):
        manifest = json.loads((version / "manifest.json").read_bytes())
        assert manifest["outputs"] == expected_outputs, "source.md is an input, not a deliverable"
        saved = version / "source.md"
        assert saved.is_file(), f"{version.name} must keep the working file as source.md"
        assert saved.read_bytes() == source, "store the working file itself, including sources and attributes"
        assert saved.resolve() != path.resolve()
        assert not saved.samefile(path), "the saved source must be an independent copy"
    saved_versions = _snapshot(path.with_suffix(".versions"))
    path.write_text("a later unsaved working file\n", encoding="utf-8")
    assert _snapshot(path.with_suffix(".versions")) == saved_versions


def _history_step(capsys, path, command, version=None):
    before = _log(path).read_bytes()
    revision = len(_entries(path)) + 1
    args = (command, path) if version is None else (command, path, version)
    code, out, err = _run(capsys, *args)
    assert code == 0, f"{command} must apply one new patch: {(out, err)}"
    assert not err
    assert re.search(rf"\b{revision}\b", out), f"print the new revision {revision}: {out!r}"
    assert _log(path).read_bytes().startswith(before), "preserve all earlier history byte for byte"
    entries = _entries(path)
    assert len(entries) == revision, "append exactly one patch per command"
    entry = entries[-1]
    assert entry["rev"] == revision and entry["file"] == path.name
    assert entry["author"] == "human"
    assert entry["ops"] and entry["inverse"], "record operations and a usable inverse, not a source overwrite"
    assert api.read_document(path).rev == revision
    if version is not None:
        assert entry["reason"] == f"restore {version}"
    return entry


@pytest.mark.parametrize(
    ("format_", "reverse", "restructure"),
    [("doc", False, False), ("doc", True, True), ("slides", False, True), ("slides", True, False)],
)
def test_cli_restore_and_undo_keep_later_edits_in_append_only_history(tmp_path, capsys, format_, reverse, restructure):
    path, v1, v2, first, second = _pair(capsys, tmp_path, format_, reverse, restructure)
    versions = _snapshot(path.with_suffix(".versions"))
    history = _log(path).read_bytes()
    # Repeat the round trip so a restore cannot truncate or replace earlier entries.
    for _ in range(2):
        restore = _history_step(capsys, path, "restore", "v1")
        assert path.read_bytes() == first
        assert api.read_document(path).sections == api.read_document(v1 / "source.md").sections
        undo = _history_step(capsys, path, "undo")
        assert undo["ops"] == restore["inverse"]
        assert path.read_bytes() == second, "undo must recover edits, added/deleted sections and their order"
        assert api.read_document(path).sections == api.read_document(v2 / "source.md").sections
        assert _log(path).read_bytes().startswith(history)
        assert _snapshot(path.with_suffix(".versions")) == versions
    # The edits made after v1 remain reachable through undo after undoing restore.
    _history_step(capsys, path, "undo")
    assert path.read_bytes() == second.replace(b"The reading is 12.", b"The reading was 12.")


@pytest.mark.parametrize("version", ["v1", "v99"], ids=["legacy-without-source", "unknown-version"])
def test_cli_restore_refuses_missing_source_or_version_without_changing_files(tmp_path, capsys, version):
    path = _working(tmp_path)
    built = _build(capsys, path, 1)
    # Simulate a pre-change version using genuine build artefacts and its old manifest.
    # The fixture stays in tmp_path, and no existing repository fixture is changed.
    (built / "source.md").unlink(missing_ok=True)
    _put(capsys, path, "The reading was 12. [S1]")
    before = _snapshot(tmp_path)
    code, out, err = _run(capsys, "restore", path, version)
    assert code == 2, (out, err)
    assert not out
    assert len(err.splitlines()) == 1 and err.strip(), "refuse cleanly, without usage or a traceback"
    assert version in err, "name the version that cannot be restored"
    if version == "v1":
        assert "source" in err.lower(), "explain why this older version cannot be restored"
    assert _snapshot(tmp_path) == before, "a refusal must not backfill or alter an immutable version"


@pytest.mark.parametrize("reverse", [False, True])
def test_cli_restore_refuses_unpatchable_front_matter_atomically(tmp_path, capsys, reverse):
    path = _working(tmp_path, reverse=reverse)
    _build(capsys, path, 1)
    _put(capsys, path, "The reading was 12. [S1]")
    path.write_bytes(path.read_bytes().replace(b"title: Working note", b"title: Revised note"))
    before = _snapshot(tmp_path)
    code, out, err = _run(capsys, "restore", path, "v1")
    assert code in (1, 2), "the current patch model cannot restore front matter"
    assert not out
    assert len(err.splitlines()) == 1 and "front" in err.lower(), "explain the front matter refusal"
    assert _snapshot(tmp_path) == before, "do not partially restore sections before refusing front matter"


@pytest.mark.parametrize(("format_", "reverse"), [("doc", False), ("slides", True)])
def test_public_restore_has_typed_result_checks_base_rev_and_uses_locked_patch_writer(
    tmp_path, capsys, monkeypatch, format_, reverse
):
    restore = getattr(api, "restore", None)
    assert callable(restore), "ai_docs_kit.api must offer restore(path, version, base_rev)"
    hints = get_type_hints(restore)
    names = {"path", "version", "base_rev", "return"}
    assert names <= hints.keys(), "type restore's inputs and result"
    assert all(hints[name] is not Any for name in names)
    assert names - {"return"} <= inspect.signature(restore).parameters.keys()
    path, _, _, first, second = _pair(capsys, tmp_path, format_, reverse)
    revision = api.read_document(path).rev
    before = _snapshot(tmp_path)
    with pytest.raises(PatchRejected) as caught:
        restore(path=path, version="v1", base_rev=revision - 1)
    assert caught.value.code == "stale-base-rev"
    assert _snapshot(tmp_path) == before
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

    history = _log(path).read_bytes()
    with monkeypatch.context() as probe:
        probe.setattr(Path, "open", observed_open)
        probe.setattr(files, "_write_atomic", observed_write)
        result = restore(path=str(path), version="v1", base_rev=revision)
    assert isinstance(result, BaseModel), "follow the public API's typed result convention"
    assert TypeAdapter(hints["return"]).validate_python(result) == result
    assert result.rev == revision + 1
    assert writes == [path], "restore must use the existing locked atomic patch writer once"
    assert path.read_bytes() == first
    assert _log(path).read_bytes().startswith(history)
    entries = _entries(path)
    assert len(entries) == revision + 1 and entries[-1]["reason"] == "restore v1"
    assert entries[-1]["author"] == "human" and entries[-1]["inverse"]
    assert api.undo(path, base_rev=result.rev).rev == result.rev + 1
    assert path.read_bytes() == second
    output = capsys.readouterr()
    assert not output.out and not output.err, "the public API must not print"
