"""`review apply`: put a decided review plan into the working file."""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from ai_docs_kit.model import Document, Item, Patch, PatchOp, Section
from ai_docs_kit.render.marks import FIELD_PATTERN, FieldError, field_value
from ai_docs_kit.review.legacy import split_legacy_wording
from ai_docs_kit.review.plan import ReviewPlan, StructureItem
from ai_docs_kit.source.files import UNPARSEABLE_RULES, apply_to_file, current_rev
from ai_docs_kit.source.ids import IdStore
from ai_docs_kit.source.parser import parse
from ai_docs_kit.source.patches import PatchRejected
from ai_docs_kit.source.read import read_source


class ApplyError(Exception):
    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


def add_apply_command(commands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    apply = commands.add_parser("apply", help="apply a decided review plan to the working file")
    apply.add_argument("file", type=Path, help="the working file")
    apply.add_argument("--plan", type=Path, required=True, help="the review plan with the person's decisions")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _paragraphs(wording: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", wording) if p.strip()]


def _load_plan(path: Path) -> ReviewPlan:
    if not path.is_file():
        raise ApplyError(f"{path}: no such plan", 2)
    try:
        return ReviewPlan.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ApplyError(f"{path}: cannot read the plan: {' '.join(str(error).split())}", 2) from error


def _load_doc(path: Path) -> Document:
    if not path.is_file():
        raise ApplyError(f"{path}: no such working file", 2)
    doc, findings = parse(read_source(path, errors="replace"))
    broken = sorted({f.rule_id for f in findings if f.rule_id in UNPARSEABLE_RULES})
    if broken:
        raise ApplyError(f"{path}: cannot be read safely: {', '.join(broken)}", 2)
    return doc


def _sent_props(path: Path, number: int) -> dict[str, dict[str, Any]]:
    composition = path.parent / f"{path.stem}.versions" / f"v{number}" / "composition.json"
    try:
        data = json.loads(composition.read_text(encoding="utf-8"))
        return {s["id"]: dict(s["props"]) for s in data["sections"] if isinstance(s.get("id"), str)}
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ApplyError(f"{composition}: cannot read the sent version: {' '.join(str(error).split())}", 2) from error


def _words(value: Any) -> str:
    return _norm(value if isinstance(value, str) else "\n\n".join(value) if isinstance(value, list) else "")


def _field_text(holder: Any, field: str) -> str | None:
    try:
        return _words(field_value(holder, field))
    except FieldError:
        return None


def _target(section: Section, field: str) -> str:
    """The field a box path stands for; a `text` box holds a section's loose words."""
    if field != "text":
        return field
    if section.title:
        return "title"
    if section.paragraphs and not section.items:
        return "paragraphs"
    raise ApplyError(f"{section.id}: the loose text box cannot be matched to one field")


def _set_field(section: Section, field: str, text: str) -> Section:
    """Return a copy of the section with the text of one field path replaced."""
    field = _target(section, field)
    if field == "paragraphs":
        return section.model_copy(update={"paragraphs": _paragraphs(text)}, deep=True)
    if not FIELD_PATTERN.fullmatch(field) or field.startswith(("image", "data")):
        raise ApplyError(f"{section.id}: the field {field} cannot be applied")
    new = section.model_copy(deep=True)
    tokens = [(n, int(i) if i else None) for n, i in re.findall(r"([a-z_]+)|\[(\d+)\]", field)]
    holder: Any = new
    for position, (name, index) in enumerate(tokens):
        last = position == len(tokens) - 1
        try:
            if index is not None:
                if last:
                    holder[index] = text
                else:
                    holder = holder[index]
            elif last:
                setattr(holder, name, text)
            else:
                holder = getattr(holder, name)
        except (IndexError, AttributeError, TypeError) as error:
            raise ApplyError(f"{section.id}: the working file has no field {field}") from error
    return new


class _Decisions:
    """What the person accepted, by section id."""

    def __init__(self, plan: ReviewPlan) -> None:
        self.titles: dict[str, str] = {}
        self.wording: dict[str, str] = {}
        self.fields: dict[str, dict[str, str]] = {}
        self.items: dict[str, list[str]] = {}
        self.proposals: dict[str, str] = {}
        self.asks: dict[str, str] = {}
        for section_id, item in plan.sections.items():
            if item.title is not None:
                self.titles[section_id] = item.title
            if item.wording is not None:
                self.wording[section_id] = item.wording
            if item.fields:
                self.fields[section_id] = item.fields
            if item.items is not None:
                self.items[section_id] = item.items
            for comment in item.confirm:
                if comment.accepted is not True:
                    continue
                if comment.action == "apply" and comment.proposal:
                    self.proposals[section_id] = comment.proposal
                elif comment.action == "redraft":
                    self.asks[section_id] = comment.ask or comment.text

    def paragraph_words(self, section_id: str) -> str | None:
        return self.proposals.get(section_id, self.wording.get(section_id))

    def rewritten(self) -> list[str]:
        return list(dict.fromkeys([*self.wording, *self.proposals, *self.fields, *self.items, *self.titles]))


def _accepted_structure(plan: ReviewPlan) -> list[StructureItem]:
    return [i for i in plan.confirm if i.accepted is True and i.action == "restructure"]


def _move_ops(order: list[str], wanted: list[str]) -> tuple[list[PatchOp], list[str]]:
    """Move sections after their wanted predecessor, touching only those not already there."""
    present = [s for s in order if s in wanted]
    target = [s for s in wanted if s in present]
    current = list(order)
    ops: list[PatchOp] = []
    moved: list[str] = []
    for previous, section_id in zip(target, target[1:], strict=False):
        if current.index(section_id) == current.index(previous) + 1:
            continue
        current.remove(section_id)
        current.insert(current.index(previous) + 1, section_id)
        ops.append(PatchOp(op="move_section", section_id=section_id, after_id=previous))
        moved.append(section_id)
    return ops, moved


def _items_text(items: Any) -> str:
    """Head, body, sub lines and citation keys, from sent props or the working file."""
    rows = []
    for item in items or []:
        if isinstance(item, dict):
            head, body, cites = item.get("head"), item.get("body"), item.get("cites") or []
            sub = item.get("sub") or []
        else:
            head, body, cites = item.head, item.body, [c.key for c in item.citations]
            sub = item.sub
        rows.append([_norm(head or ""), _norm(body or ""), [_norm(s) for s in sub], [str(c) for c in cites]])
    return json.dumps(rows)


def _word_text(item: Item, *, legacy: bool = False) -> str:
    """The item as the Word copy writes it: head and body joined by a colon, then the sub lines."""
    head = item.head if legacy else (item.head or "").rstrip(":")
    text = f"{head}: {item.body}" if head else item.body
    return _norm(" ".join([text, *item.sub]))


def _edited(item: Item, text: str) -> Item | None:
    """Keep metadata when the head or the body is unchanged, accepting older double-colon copies."""
    body = _norm(text)
    head = item.head
    if head:
        prefixes = (f"{head}: ", f"{head.rstrip(':')}: ")
        prefix = next((p for p in prefixes if body.startswith(p)), None)
        suffix = _norm(" ".join([item.body, *item.sub]))
        if suffix and body.endswith(f": {suffix}"):
            # The unchanged body locates the separator even when either field contains a colon.
            head, body = body[: -len(suffix) - 2], suffix
            if item.head and item.head.endswith(":"):
                head = head.rstrip(":") + ":"
        elif prefix is not None:
            body = body[len(prefix) :]
        elif body == head:
            body = ""
        else:
            return None
    tail = _norm(" ".join(item.sub))
    if tail and body.endswith(tail):
        body = body[: -len(tail)].strip()
    return item.model_copy(update={"head": head, "body": body}, deep=True)


def _items_for(section: Section, texts: list[str]) -> list[Item]:
    """The section's items for the reviewed list texts.

    Match unchanged items first, then edits with an unchanged head or body. A sole remaining plain
    bullet keeps its metadata when reworded. Other unmatched texts are new items.
    """
    pool = list(section.items)
    result: list[Item | None] = [None] * len(texts)
    for position, text in enumerate(texts):
        match = next((i for i in pool if _norm(text) in (_word_text(i), _word_text(i, legacy=True))), None)
        if match is not None:
            pool.remove(match)
            result[position] = match
    for position, text in enumerate(texts):
        if result[position] is not None:
            continue
        for item in pool:
            edited = _edited(item, text) if item.head else None
            if edited is not None:
                pool.remove(item)
                result[position] = edited
                break
    remaining = [position for position, item in enumerate(result) if item is None]
    if len(pool) == len(remaining) == 1 and not pool[0].head:
        result[remaining[0]] = _edited(pool[0], texts[remaining[0]])
    return [item if item is not None else Item(body=texts[position]) for position, item in enumerate(result)]


def _changed_parts(
    by_id: dict[str | None, Section], sent: dict[str, dict[str, Any]], decided: _Decisions
) -> dict[str, list[str]]:
    """Touched sections whose title, paragraphs, items or deck fields differ from the sent version, with the parts."""
    changed: dict[str, list[str]] = {}
    touched = {*decided.rewritten(), *decided.asks}
    for section_id in sorted(touched):
        props, section = sent.get(section_id, {}), by_id[section_id]
        parts: list[str] = []
        if "title" in props and _words(props["title"]) != _words(section.title):
            parts.append("title")
        if _words(props.get("paragraphs")) != _words(section.paragraphs):
            parts.append("paragraphs")
        if "items" in props and _items_text(props["items"]) != _items_text(section.items):
            parts.append("items")
        for field in decided.fields.get(section_id, {}):
            target = _target(section, field)
            before, now = _field_text(props, target), _field_text(section, target)
            if before is not None and before != now and target not in parts:
                parts.append(target)
        if parts:
            changed[section_id] = parts
    return changed


def apply_plan(path: Path, plan_path: Path) -> tuple[dict[str, list[str]], list[str]]:
    plan = _load_plan(plan_path)
    doc = _load_doc(path)
    split_legacy_wording(plan, doc.sections)
    by_id = {s.id: s for s in doc.sections}
    decided = _Decisions(plan)
    structure = _accepted_structure(plan)
    deletes = [i.section for i in structure if i.kind == "delete" and i.section]
    touched = [*decided.rewritten(), *decided.asks, *deletes]
    missing = sorted({s for s in touched if s not in by_id})
    for section_id in missing:
        decided.titles.pop(section_id, None)
        decided.wording.pop(section_id, None)
        decided.fields.pop(section_id, None)
        decided.items.pop(section_id, None)
        decided.proposals.pop(section_id, None)
        decided.asks.pop(section_id, None)
    deletes = [s for s in deletes if s in by_id]
    changed = _changed_parts(by_id, _sent_props(path, plan.version), decided)
    notes = [f"changed since v{plan.version}: {i} ({', '.join(parts)})" for i, parts in changed.items()]
    notes.extend(f"missing: {i}" for i in missing)
    ops: list[PatchOp] = []
    applied: list[str] = []
    for section_id in decided.rewritten():
        new = by_id[section_id]
        if section_id in decided.titles:
            new = new.model_copy(update={"title": decided.titles[section_id]}, deep=True)
        words = decided.paragraph_words(section_id)
        if words is not None:
            new = new.model_copy(update={"paragraphs": _paragraphs(words)}, deep=True)
        if section_id in decided.items:
            new = new.model_copy(update={"items": _items_for(new, decided.items[section_id])}, deep=True)
        for field, text in decided.fields.get(section_id, {}).items():
            new = _set_field(new, field, text)
        new.owner = "human"
        ops.append(PatchOp(op="replace_section", section_id=section_id, value=new))
        applied.append(section_id)
    redrafted = [s for s in decided.asks if s not in deletes]
    ops.extend(
        PatchOp(op="set_attr", section_id=s, fields={"name": "redraft", "value": decided.asks[s]}) for s in redrafted
    )
    ops.extend(PatchOp(op="delete_section", section_id=s) for s in deletes)
    order = [s.id for s in doc.sections if s.id and s.id not in deletes]
    moved: list[str] = []
    for item in structure:
        if item.kind == "reorder" and item.order:
            move_ops, ids = _move_ops(order, [s for s in item.order if s not in deletes])
            ops.extend(move_ops)
            moved.extend(ids)
            order = _simulate(order, move_ops)
    applied = [s for s in applied if s not in deletes]
    if ops:
        store = path.parent / ".ai_docs_kit"
        oplog = store / "oplog.jsonl"
        patch = Patch(base_rev=current_rev(oplog), author="human", reason="review apply", ops=ops)
        try:
            apply_to_file(path, patch, oplog, IdStore(store / "ids.json"))
        except PatchRejected as error:
            raise ApplyError(str(error)) from error
    return {"applied": applied, "redrafted": redrafted, "moved": moved, "deleted": deletes}, notes


def _simulate(order: list[str], ops: list[PatchOp]) -> list[str]:
    current = list(order)
    for op in ops:
        current.remove(op.section_id)
        current.insert(current.index(op.after_id or "") + 1, op.section_id)
    return current


def run_apply(args: argparse.Namespace) -> int:
    try:
        touched, notes = apply_plan(args.file, args.plan)
    except ApplyError as error:
        print(error, file=sys.stderr)
        return error.code
    except (OSError, ValueError) as error:
        print(" ".join(str(error).split()), file=sys.stderr)
        return 2
    print(f"applied the plan to {args.file}")
    for note in notes:
        print(note)
    print("touched " + json.dumps(touched))
    return 0
