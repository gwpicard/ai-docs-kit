import json
import os
import re
from collections.abc import Collection, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from threading import local
from typing import Literal

from pydantic import BaseModel

from ai_docs_kit.model import Document, Patch, PatchOp
from ai_docs_kit.source.atomic import write_atomic as _write_atomic
from ai_docs_kit.source.ids import IdStore, stamp
from ai_docs_kit.source.parser import parse
from ai_docs_kit.source.patches import FactGuard, PatchRejected, apply_patch, inverse_ops
from ai_docs_kit.source.read import read_source
from ai_docs_kit.source.serialiser import serialise

UNPARSEABLE_RULES = ("source.parse-error", "source.appearance-in-source")


class _Locks(local):
    def __init__(self) -> None:
        self.held: set[tuple[int, int, int]] = set()


_locks = _Locks()


@contextmanager
def project_lock(directory: Path) -> Iterator[None]:
    """Lock the shared store, allowing nested patch calls in the same thread."""
    try:
        import fcntl
    except ImportError as error:
        raise OSError("working-file locking requires fcntl (macOS or Linux)") from error

    directory.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        stat = os.fstat(descriptor)
        key = (os.getpid(), stat.st_dev, stat.st_ino)
        if key in _locks.held:
            yield
            return
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        _locks.held.add(key)
        try:
            yield
        finally:
            _locks.held.remove(key)
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def current_rev(oplog: Path) -> int:
    """The revision is the number of non-empty lines in the log; 0 when there is no log."""
    if not oplog.exists():
        return 0
    return sum(1 for line in oplog.read_text(encoding="utf-8").splitlines() if line.strip())


def _write_logged(
    oplog: Path,
    path: Path,
    patch: Patch,
    result: Document,
    before: Document,
    *,
    kept: Mapping[str, Collection[str]] | None = None,
) -> None:
    text = serialise(result)
    inverse = inverse_ops(before, patch, kept=kept)
    entry = {
        "rev": result.rev,
        "author": patch.author,
        "reason": patch.reason,
        "finding_ids": patch.finding_ids,
        "ops": [op.model_dump(mode="json") for op in patch.ops],
        "file": path.name,
        "inverse": [op.model_dump(mode="json") for op in inverse] if inverse is not None else None,
    }
    line = json.dumps(entry, sort_keys=True) + "\n"
    oplog.parent.mkdir(parents=True, exist_ok=True)
    with oplog.open("a", encoding="utf-8", newline="\n") as handle:
        offset = handle.tell()
        try:
            # Record the inverse before replacing the working file.
            handle.write(line)
            handle.flush()
            _write_atomic(path, text)
        except BaseException:
            # A failed replacement must not leave a history entry for an unapplied patch.
            handle.seek(offset)
            handle.truncate()
            raise


def _parse_editable(path: Path) -> Document:
    doc, findings = parse(read_source(path))
    broken = sorted({f.rule_id for f in findings if f.rule_id in UNPARSEABLE_RULES})
    if broken:
        raise PatchRejected("unparseable", f"{path.name} cannot be edited safely: {', '.join(broken)}")
    return doc


def apply_to_file(
    path: Path,
    patch: Patch,
    oplog: Path,
    ids: IdStore,
    fact_guard: FactGuard | None = None,
    *,
    kept: Mapping[str, Collection[str]] | None = None,
) -> Document:
    """Apply `patch` to the working file at `path` and append the change to `oplog`."""
    with project_lock(oplog.parent):
        doc = _parse_editable(path)
        ids.issued.update(IdStore(ids.path).issued)
        stamped, _ = stamp(doc, ids)
        stamped = stamped.model_copy(update={"rev": current_rev(oplog)})
        result = apply_patch(stamped, patch, fact_guard, kept=kept)
        ids.save()
        _write_logged(oplog, path, patch, result, stamped, kept=kept)
        return result


def apply_to_document(path: Path, before: Document, patch: Patch, oplog: Path, ids: IdStore) -> Document:
    """Apply a patch to the last good document and persist it."""
    with project_lock(oplog.parent):
        revision = current_rev(oplog)
        if before.rev != revision:
            raise PatchRejected("stale-base-rev", f"document is at rev {revision}, not {before.rev}; read it again")
        ids.issued.update(IdStore(ids.path).issued)
        patch = patch.model_copy(deep=True)
        replacements: dict[str, str] = {}
        existing = {s.id for s in before.sections if s.id is not None}
        for op in patch.ops:
            if op.after_id in replacements:
                op.after_id = replacements[op.after_id]
            if op.section_id in replacements:
                op.section_id = replacements[op.section_id]
            if op.op == "insert_after" and op.value is not None and op.value.id is None:
                new_id = ids.allocate(existing=existing)
                existing.add(new_id)
                replacements[op.section_id] = new_id
                op.section_id = new_id
                op.value.id = new_id
        result = apply_patch(before, patch)
        ids.save()
        _write_logged(oplog, path, patch, result, before)
        return result


class _LogEntry(BaseModel):
    rev: int
    file: str
    reason: str
    ops: list[PatchOp]
    inverse: list[PatchOp] | None = None


def _history_target(oplog: Path, name: str, command: Literal["undo", "redo"]) -> _LogEntry:
    done: list[_LogEntry] = []
    undone: list[_LogEntry] = []
    if oplog.exists():
        for line in oplog.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = _LogEntry.model_validate_json(line)
            if entry.file != name:
                continue
            action = re.fullmatch(r"(undo|redo) rev ([1-9][0-9]*)", entry.reason)
            if action is None:
                done.append(entry)
                undone.clear()
                continue
            source, destination = (done, undone) if action[1] == "undo" else (undone, done)
            if not source or source[-1].rev != int(action[2]):
                raise ValueError(f"invalid {name} history at rev {entry.rev}")
            destination.append(source.pop())
    candidates = done if command == "undo" else undone
    if not candidates:
        raise PatchRejected(f"nothing-to-{command}", f"nothing to {command} for {name}")
    target = candidates[-1]
    if command == "undo" and target.inverse is None:
        raise PatchRejected("no-inverse", f"cannot undo rev {target.rev}: no recorded inverse")
    return target


def apply_history(path: Path, command: Literal["undo", "redo"], base_rev: int | None = None) -> tuple[Document, int]:
    """Replay one file's history as a new human patch under the project lock."""
    store = path.parent / ".ai_docs_kit"
    oplog = store / "oplog.jsonl"
    with project_lock(store):
        before = _parse_editable(path).model_copy(update={"rev": current_rev(oplog)})
        if base_rev is not None and base_rev != before.rev:
            raise PatchRejected("stale-base-rev", f"document is at rev {before.rev}, not {base_rev}; read it again")
        target = _history_target(oplog, path.name, command)
        ops = target.inverse if command == "undo" else target.ops
        assert ops is not None
        patch = Patch(base_rev=before.rev, author="human", reason=f"{command} rev {target.rev}", ops=ops)
        result = apply_to_document(path, before, patch, oplog, IdStore(store / "ids.json"))
        return result, target.rev
