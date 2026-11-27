"""Patch callers keep their snapshot, id store and lock lifetime consistent."""

import fcntl
import json
import os
import random
from pathlib import Path

import pytest

from ai_docs_kit import section_command
from ai_docs_kit.cli import main
from ai_docs_kit.model import Patch, PatchOp
from ai_docs_kit.source import files
from ai_docs_kit.source.ids import IdStore
from ai_docs_kit.source.parser import parse
from ai_docs_kit.source.patches import PatchRejected


def _seed(root, name="note", *, idless=False):
    path = root / f"{name}.md"
    path.write_text(
        "---\ndoctype: report\nformat: doc\n---\n\n"
        '::: {#anchor .section intent="statement"}\n## Title\n\noriginal wording\n:::\n'
        + ('\n::: {.section intent="statement"}\n## Other\n:::\n' if idless else ""),
        encoding="utf-8",
    )
    oplog = root / ".ai_docs_kit" / "oplog.jsonl"
    return path, oplog, IdStore(oplog.parent / "ids.json", rng=random.Random(1))


def _patch(revision, wording="revised wording"):
    return Patch(
        base_rev=revision,
        author="human",
        reason="lock recovery test",
        ops=[PatchOp(op="set_fields", section_id="anchor", fields={"paragraphs": [wording]})],
    )


def _locked(directory):
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        return False
    finally:
        os.close(descriptor)


def test_last_good_snapshot_cannot_overwrite_a_newer_file_even_with_a_current_patch(tmp_path):
    path, oplog, store = _seed(tmp_path)
    snapshot, _ = parse(path.read_text(encoding="utf-8"))
    current = files.apply_to_file(path, _patch(0), oplog, store)
    before = {p: p.read_bytes() for p in (path, oplog, store.path)}
    with pytest.raises(PatchRejected, match="stale-base-rev"):
        files.apply_to_document(path, snapshot, _patch(1, "stale wording"), oplog, store)
    assert {p: p.read_bytes() for p in before} == before
    assert not _locked(oplog.parent)
    result = files.apply_to_document(path, current, _patch(1, "latest wording"), oplog, store)
    assert result.rev == 2
    assert result.sections[0].paragraphs == ["latest wording"]


def test_store_opened_before_another_writer_retains_issued_ids_across_working_files(tmp_path):
    first, oplog, first_store = _seed(tmp_path, "first", idless=True)
    second, _, second_store = _seed(tmp_path, "second", idless=True)
    first_doc = files.apply_to_file(first, _patch(0), oplog, first_store)
    second_doc = files.apply_to_file(second, _patch(1), oplog, second_store)
    first_id, second_id = first_doc.sections[1].id, second_doc.sections[1].id
    assert first_id != second_id
    assert set(json.loads(first_store.path.read_text(encoding="utf-8"))["issued"]) == {first_id, second_id}


def test_patch_saves_complete_id_store_by_atomic_replacement(tmp_path, monkeypatch):
    path, oplog, store = _seed(tmp_path, idless=True)
    store.issued.add("00000")
    store.save()
    replace = os.replace
    observations = []

    def observe_replace(source, target):
        if target == store.path:
            assert json.loads(store.path.read_text(encoding="utf-8"))["issued"] == ["00000"]
            assert len(json.loads(Path(source).read_text(encoding="utf-8"))["issued"]) == 2
            observations.append("ids")
        return replace(source, target)

    monkeypatch.setattr(os, "replace", observe_replace)
    result = files.apply_to_file(path, _patch(0), oplog, store)
    assert observations == ["ids"]
    assert set(json.loads(store.path.read_text(encoding="utf-8"))["issued"]) == {"00000", result.sections[1].id}
    assert sorted(p.name for p in oplog.parent.iterdir()) == ["ids.json", "oplog.jsonl"]


@pytest.mark.parametrize("entry_point", ["file", "document"])
def test_failed_replacement_rolls_back_log_and_releases_lock_before_retry(tmp_path, monkeypatch, entry_point):
    path, oplog, store = _seed(tmp_path)
    snapshot, _ = parse(path.read_text(encoding="utf-8"))
    before = path.read_bytes()

    def apply():
        if entry_point == "file":
            return files.apply_to_file(path, _patch(0), oplog, store)
        return files.apply_to_document(path, snapshot, _patch(0), oplog, store)

    def fail_write(*_args):
        assert _locked(oplog.parent)
        raise OSError("replacement refused")

    with monkeypatch.context() as patcher:
        patcher.setattr(files, "_write_atomic", fail_write)
        with pytest.raises(OSError, match="replacement refused"):
            apply()
    assert path.read_bytes() == before
    assert oplog.read_bytes() == b""
    assert not _locked(oplog.parent)
    assert apply().rev == 1
    assert files.current_rev(oplog) == 1
    assert not _locked(oplog.parent)


def test_section_put_reads_working_file_and_prepares_guard_inside_lock(tmp_path, monkeypatch):
    path, oplog, _ = _seed(tmp_path)
    replacement = tmp_path / "replacement.md"
    replacement.write_text(
        '::: {#anchor .section intent="statement"}\n## Title\n\nrevised wording\n:::\n', encoding="utf-8"
    )
    load, guard = section_command._load, section_command.FactGuard
    observations = []

    def load_locked(*args, **kwargs):
        observations.append("read")
        assert _locked(oplog.parent)
        return load(*args, **kwargs)

    def guard_locked(*args, **kwargs):
        observations.append("guard")
        assert _locked(oplog.parent)
        return guard(*args, **kwargs)

    monkeypatch.setattr(section_command, "_load", load_locked)
    monkeypatch.setattr(section_command, "FactGuard", guard_locked)
    assert main(["section", "put", str(path), "anchor", "--from", str(replacement)]) == 0
    assert observations == ["read", "guard"]
    assert not _locked(oplog.parent)
