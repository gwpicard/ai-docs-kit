"""`ai-docs-kit section get|put|list`: read and replace one section through the patch guards."""

import argparse
import sys
from pathlib import Path

from ai_docs_kit.loop.guards import FactGuard, _fields
from ai_docs_kit.model import Document, Patch, PatchOp, Section
from ai_docs_kit.source.files import UNPARSEABLE_RULES, apply_to_file, current_rev
from ai_docs_kit.source.ids import IdStore
from ai_docs_kit.source.parser import parse
from ai_docs_kit.source.patches import PatchRejected
from ai_docs_kit.source.serialiser import _section


class _Refused(Exception):
    """A section command that cannot go ahead; the message is for the person."""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


def add_section_commands(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    section = subparsers.add_parser("section", help="read and replace one section of a working file")
    commands = section.add_subparsers(dest="section_command", required=True)
    listing = commands.add_parser("list", help="print every section id with its intent, owner and redraft ask")
    listing.add_argument("file", type=Path, help="the working file")
    get = commands.add_parser("get", help="print one section with the sources it cites")
    get.add_argument("file", type=Path, help="the working file")
    get.add_argument("id", help="the section id")
    put = commands.add_parser("put", help="replace one section through the patch guards")
    put.add_argument("file", type=Path, help="the working file")
    put.add_argument("id", help="the section id")
    put.add_argument("--from", dest="source", type=Path, required=True, help="a file holding the new section block")
    put.add_argument("--redraft-done", action="store_true", help="remove the redraft ask and record because=")


def _load(path: Path) -> Document:
    if not path.is_file():
        raise _Refused(f"{path}: no such working file", 2)
    doc, findings = parse(path.read_bytes().decode("utf-8", errors="replace"))
    broken = sorted({f.rule_id for f in findings if f.rule_id in UNPARSEABLE_RULES})
    if broken:
        raise _Refused(f"{path}: cannot be read safely: {', '.join(broken)}", 2)
    return doc


def _find(doc: Document, section_id: str) -> Section:
    for section in doc.sections:
        if section.id == section_id:
            return section
    raise _Refused(f"no section with id {section_id!r}")


def _list(doc: Document) -> int:
    for section in doc.sections:
        if section.id is None:
            continue
        line = f"{section.id}  {section.intent}  {section.owner or '-'}"
        if section.lock:
            line += f"  lock={section.lock}"
        if section.redraft:
            line += f'  redraft="{section.redraft}"'
        print(line)
    return 0


def _get(doc: Document, section_id: str) -> int:
    section = _find(doc, section_id)
    cited = {c.key for item in section.items for c in item.citations}
    print(_section(section))
    print()
    print("## Sources")
    print()
    for source in doc.sources:
        if source.key in cited:
            print(f"- [{source.key}] {source.text}")
    return 0


def _replacement(path: Path) -> Section:
    if not path.is_file():
        raise _Refused(f"{path}: no such file", 2)
    doc, _ = parse(path.read_bytes().decode("utf-8", errors="replace"))
    if len(doc.sections) != 1:
        raise _Refused(f"{path}: must hold exactly one section block, found {len(doc.sections)}")
    return doc.sections[0]


def _check_may_replace(old: Section) -> None:
    if old.owner == "human":
        raise _Refused(f'section {old.id} is marked owner="human"; a person wrote it, so it stays as it is')
    if old.lock:
        raise _Refused(f"section {old.id} is locked (lock={old.lock}); unlock it before it is replaced")


def _put(path: Path, doc: Document, args: argparse.Namespace) -> int:
    old = _find(doc, args.id)
    _check_may_replace(old)
    new = _replacement(args.source)
    new.owner, new.lock = old.owner, old.lock
    if args.redraft_done:
        new.redraft = None
        new.because = new.because or old.because
    else:
        new.redraft = old.redraft
    evidence = [f"{s.key} {s.text}" for s in doc.sources]
    evidence.extend(v for v in doc.front.values() if isinstance(v, str))
    evidence.extend(_fields(old))
    guard = FactGuard(evidence, {s.key for s in doc.sources})
    store = path.parent / ".ai_docs_kit"
    oplog = store / "oplog.jsonl"
    patch = Patch(
        base_rev=current_rev(oplog),
        author="ai",
        reason="section put" + (" (redraft done)" if args.redraft_done else ""),
        ops=[PatchOp(op="replace_section", section_id=args.id, value=new)],
    )
    try:
        apply_to_file(path, patch, oplog, IdStore(store / "ids.json"), guard)
    except PatchRejected as error:
        detail = f" ({', '.join(guard.unsupported)})" if error.code == "fact-unsupported" else ""
        raise _Refused(f"{error}{detail}") from error
    print(f"replaced section {args.id}")
    return 0


def run_section(args: argparse.Namespace) -> int:
    try:
        doc = _load(args.file)
        if args.section_command == "list":
            return _list(doc)
        if args.section_command == "get":
            return _get(doc, args.id)
        return _put(args.file, doc, args)
    except _Refused as error:
        print(error, file=sys.stderr)
        return error.code
