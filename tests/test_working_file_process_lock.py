"""Issue 373: directory locks protect the whole working-file patch transaction.

The file/oplog oracle is tests/judge/test_m1_4b_files.py. Process barriers
force an overlapping replacement when no advisory lock is held, so the
lock-disabled control cannot pass merely because the scheduler ran serially.
"""

import fcntl
import json
import multiprocessing
import os
import subprocess
import sys
import traceback
from pathlib import Path

import pytest

from ai_docs_kit import section_command
from ai_docs_kit.cli import main
from ai_docs_kit.model import Patch, PatchOp
from ai_docs_kit.source import files
from ai_docs_kit.source.ids import IdStore
from ai_docs_kit.source.parser import parse
from ai_docs_kit.source.patches import PatchRejected


def _seed(root, *, reverse=False, format="doc"):
    root.mkdir(parents=True, exist_ok=True)
    sections = [
        f'::: {{#{key} .section intent="statement"}}\n## {key}\n\noriginal wording\n:::\n' for key in ("left", "right")
    ]
    if reverse:
        sections.reverse()
    path = root / "note.md"
    path.write_text(
        f"---\ndoctype: report\nformat: {format}\ntitle: Test note\n---\n\n" + "\n".join(sections),
        encoding="utf-8",
    )
    return path, root / ".ai_docs_kit" / "oplog.jsonl"


def _patch(base_rev, section_id="left", paragraphs=None):
    return Patch(
        base_rev=base_rev,
        author="human",
        reason="process lock test",
        ops=[PatchOp(op="set_fields", section_id=section_id, fields={"paragraphs": paragraphs or ["changed wording"]})],
    )


def _directory_locked(directory, flock=fcntl.flock):
    """Probe through a distinct descriptor, including in the lock owner's process."""
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        try:
            flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        flock(descriptor, fcntl.LOCK_UN)
        return False
    finally:
        os.close(descriptor)


def _stop(processes):
    for process in processes:
        process.join(timeout=2)
        if process.is_alive():
            process.terminate()
            process.join(timeout=3)
        if process.is_alive():
            process.kill()
            process.join(timeout=3)
        process.close()


def _blocked_writer(path, oplog, entry_point, starting, reading, connection):
    try:
        before, _ = parse(path.read_text(encoding="utf-8"))
        store = IdStore(oplog.parent / "ids.json")
        observations = []

        def observe(name, function):
            def wrapped(*args, **kwargs):
                reading.set()
                observations.append((name, _directory_locked(oplog.parent)))
                assert set(p.name for p in oplog.parent.iterdir()) <= {"ids.json", "oplog.jsonl"}
                return function(*args, **kwargs)

            return wrapped

        with pytest.MonkeyPatch.context() as patcher:
            for name in ("_parse_editable", "current_rev", "apply_patch", "_write_atomic"):
                patcher.setattr(files, name, observe(name, getattr(files, name)))
            patcher.setattr(IdStore, "save", observe("ids.save", IdStore.save))
            starting.set()
            if entry_point == "apply_to_file":
                files.apply_to_file(path, _patch(0), oplog, store)
            else:
                files.apply_to_document(path, before, _patch(0), oplog, store)
        connection.send({"observations": observations})
    except BaseException:
        connection.send({"error": traceback.format_exc()})
    finally:
        connection.close()


@pytest.mark.parametrize("entry_point", ["apply_to_file", "apply_to_document"])
def test_patch_waits_for_directory_lock_before_reading_and_holds_it_through_write(tmp_path, entry_point):
    path, oplog = _seed(tmp_path)
    oplog.parent.mkdir()
    before = path.read_bytes()
    context = multiprocessing.get_context("spawn")
    starting, reading = context.Event(), context.Event()
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=_blocked_writer, args=(path, oplog, entry_point, starting, reading, send))
    descriptor = os.open(oplog.parent, os.O_RDONLY)
    fcntl.flock(descriptor, fcntl.LOCK_EX)
    process.start()
    send.close()
    try:
        assert starting.wait(15), "writer did not reach the patch entry point"
        assert not reading.wait(0.5), f"{entry_point} read while another process held the directory lock"
        assert path.read_bytes() == before
        assert list(oplog.parent.iterdir()) == [], "waiting for the lock must not create a lock file"
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        assert receive.poll(15), "writer did not resume after the directory lock was released"
        report = receive.recv()
        assert "error" not in report, report
        observations = report["observations"]
        assert {name for name, _ in observations} >= {"current_rev", "apply_patch", "ids.save", "_write_atomic"}
        if entry_point == "apply_to_file":
            assert "_parse_editable" in {name for name, _ in observations}
        assert all(held for _, held in observations), observations
        assert "changed wording" in path.read_text(encoding="utf-8")
        assert files.current_rev(oplog) == 1
        assert sorted(p.name for p in oplog.parent.iterdir()) == ["ids.json", "oplog.jsonl"]
        assert sorted(p.name for p in path.parent.iterdir()) == [".ai_docs_kit", "note.md"]
        assert not _directory_locked(oplog.parent), "the completed patch left its lock held"
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
        _stop([process])
        receive.close()


def _writer(path, oplog, section_id, barrier, disable_lock, connection):
    try:
        store = IdStore(oplog.parent / "ids.json")
        write_atomic = files._write_atomic

        def overlapping_write(target, text):
            # Both replacements have passed the guards before either is allowed
            # to replace the file. A real lock serialises this checkpoint.
            # The probe itself takes a lock, so disabled controls must bypass it.
            if disable_lock or not _directory_locked(oplog.parent):
                barrier.wait(timeout=15)
            return write_atomic(target, text)

        with pytest.MonkeyPatch.context() as patcher:
            if disable_lock:
                patcher.setattr(fcntl, "flock", lambda *_args: None)
            patcher.setattr(files, "_write_atomic", overlapping_write)
            barrier.wait(timeout=15)
            for number in range(20):
                paragraphs = [f"{section_id} write {index:02d}" for index in range(number + 1)]
                for _ in range(100):
                    patch = _patch(files.current_rev(oplog), section_id, paragraphs)
                    try:
                        files.apply_to_file(path, patch, oplog, store)
                    except PatchRejected as error:
                        if error.code != "stale-base-rev":
                            raise
                        # Explicit-base callers reread and retry when another
                        # writer acquired the lock first. No accepted write is dropped.
                        continue
                    break
                else:
                    raise AssertionError("writer could not obtain a current base revision")
        connection.send({"writes": 20})
    except BaseException:
        connection.send({"error": traceback.format_exc()})
    finally:
        connection.close()


def _two_writers(root, reverse, disable_lock):
    path, oplog = _seed(root, reverse=reverse)
    IdStore(oplog.parent / "ids.json").save()
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    processes, connections = [], []
    try:
        for section_id in ("left", "right"):
            receive, send = context.Pipe(duplex=False)
            process = context.Process(target=_writer, args=(path, oplog, section_id, barrier, disable_lock, send))
            process.start()
            send.close()
            processes.append(process)
            connections.append(receive)
        for receive in connections:
            assert receive.poll(25), "writer did not finish its twenty patches"
            report = receive.recv()
            assert report == {"writes": 20}, report
        for process in processes:
            process.join(timeout=5)
            assert process.exitcode == 0, "writer process failed"
        entries = [json.loads(line) for line in oplog.read_text(encoding="utf-8").splitlines()]
        doc, findings = parse(path.read_text(encoding="utf-8"))
        assert not findings, findings
        return doc, entries
    finally:
        _stop(processes)
        for receive in connections:
            receive.close()


def _assert_every_write(doc, entries):
    assert len(entries) == 40, f"lost oplog entries: expected 40, got {len(entries)}"
    sections = {section.id: section for section in doc.sections}
    missing = [
        f"{key} write {number:02d}"
        for key in ("left", "right")
        for number in range(20)
        if f"{key} write {number:02d}" not in sections[key].paragraphs
    ]
    assert not missing, f"lost writes from the final working file: {missing}"


@pytest.mark.parametrize("reverse", [False, True], ids=["left-first", "right-first"])
def test_two_processes_preserve_forty_writes_and_disabling_the_lock_loses_writes(tmp_path, reverse):
    unlocked_doc, unlocked_entries = _two_writers(tmp_path / "unlocked", reverse, disable_lock=True)
    with pytest.raises(AssertionError, match="lost writes from the final working file"):
        _assert_every_write(unlocked_doc, unlocked_entries)

    doc, entries = _two_writers(tmp_path / "locked", reverse, disable_lock=False)
    _assert_every_write(doc, entries)
    assert [entry["rev"] for entry in entries] == list(range(1, 41))
    assert {entry["file"] for entry in entries} == {"note.md"}


def _replacement(root, section_id, wording):
    source = root / "replacement.md"
    source.write_text(
        f'::: {{#{section_id} .section intent="statement"}}\n## {section_id}\n\n{wording}\n:::\n',
        encoding="utf-8",
    )
    return source


def _put(path, section_id, source, *extra):
    return subprocess.run(
        [
            str(Path(sys.executable).with_name("ai-docs-kit")),
            "section",
            "put",
            str(path),
            section_id,
            "--from",
            str(source),
            *extra,
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


@pytest.mark.parametrize(("format", "reverse", "section_id"), [("doc", False, "right"), ("slides", True, "left")])
def test_section_put_accepts_current_base_and_refuses_past_base_without_changing_file_or_oplog(
    tmp_path, format, reverse, section_id
):
    path, oplog = _seed(tmp_path, format=format, reverse=reverse)
    for revision, wording in enumerate(("original wording", "revised wording")):
        source = _replacement(tmp_path, section_id, wording)
        result = _put(path, section_id, source, "--base-rev", str(revision))
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""
        assert files.current_rev(oplog) == revision + 1

    source = _replacement(tmp_path, section_id, "stale wording")
    before = {p: p.read_bytes() for p in (path, oplog, oplog.parent / "ids.json")}
    for stale_revision in (0, 1):
        result = _put(path, section_id, source, "--base-rev", str(stale_revision))
        assert result.returncode == 1, result.stderr
        assert result.stderr.splitlines() == [f"document is at rev 2, not {stale_revision}; read it again"]
        assert {p: p.read_bytes() for p in before} == before
    result = _put(path, section_id, source, "--base-rev", "2")
    assert result.returncode == 0, result.stderr
    assert files.current_rev(oplog) == 3


@pytest.mark.parametrize("reverse", [False, True], ids=["left-first", "right-first"])
def test_section_put_without_base_reads_revision_inside_lock_and_still_accepts_repeated_edits(
    tmp_path, monkeypatch, reverse
):
    path, oplog = _seed(tmp_path, reverse=reverse)
    observations = []
    current_rev = files.current_rev

    def observed_revision(log):
        held = log.parent.exists() and _directory_locked(log.parent)
        observations.append(held)
        return current_rev(log)

    monkeypatch.setattr(files, "current_rev", observed_revision)
    monkeypatch.setattr(section_command, "current_rev", observed_revision, raising=False)
    for section_id in ("right", "left"):
        source = _replacement(tmp_path, section_id, "revised wording")
        assert main(["section", "put", str(path), section_id, "--from", str(source)]) == 0
    assert current_rev(oplog) == 2
    assert observations and all(observations), f"revision reads outside the directory lock: {observations}"
    doc, _ = parse(path.read_text(encoding="utf-8"))
    assert all(section.paragraphs == ["revised wording"] for section in doc.sections)


def test_section_put_without_fcntl_refuses_clearly_instead_of_writing_unlocked(tmp_path):
    path, oplog = _seed(tmp_path)
    source = _replacement(tmp_path, "left", "revised wording")
    before = path.read_bytes()
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.modules['fcntl'] = None; from ai_docs_kit.cli import main; sys.exit(main(sys.argv[1:]))",
            "section",
            "put",
            str(path),
            "left",
            "--from",
            str(source),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode in (1, 2), "section put wrote without advisory locking support"
    assert len(result.stderr.splitlines()) == 1, result.stderr
    assert "fcntl" in result.stderr.lower() or "locking" in result.stderr.lower(), result.stderr
    assert "Traceback" not in result.stderr
    assert path.read_bytes() == before
    assert not oplog.exists()
