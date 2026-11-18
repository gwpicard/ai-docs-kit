"""`review apply`: put a decided review plan into the working file."""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from ai_docs_kit.model import Document, Item, Patch, PatchOp, Section
from ai_docs_kit.render.marks import FIELD_PATTERN, FieldError, field_value
from ai_docs_kit.review.plan import ReviewPlan, StructureItem
from ai_docs_kit.source.files import UNPARSEABLE_RULES, apply_to_file, current_rev
from ai_docs_kit.source.ids import IdStore
from ai_docs_kit.source.parser import parse
from ai_docs_kit.source.patches import PatchRejected


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
    doc, findings = parse(path.read_bytes().decode("utf-8", errors="replace"))
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
        self.wording: dict[str, str] = {}
        self.fields: dict[str, dict[str, str]] = {}
        self.items: dict[str, list[str]] = {}
        self.proposals: dict[str, str] = {}
        self.asks: dict[str, str] = {}
        for section_id, item in plan.sections.items():
            if item.wording:
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
        return self.proposals.get(section_id) or self.wording.get(section_id)

    def rewritten(self) -> list[str]:
        return [
            *self.wording,
            *(s for s in self.proposals if s not in self.wording),
            *(s for s in self.fields if s not in self.wording and s not in self.proposals),
            *(s for s in self.items if s not in self.wording and s not in self.proposals and s not in self.fields),
        ]


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
    """Head, body and citation keys of each item, the same from the sent props and from the working file."""
    rows = []
    for item in items or []:
        if isinstance(item, dict):
            head, body, cites = item.get("head"), item.get("body"), item.get("cites") or []
        else:
            head, body, cites = item.head, item.body, [c.key for c in item.citations]
        rows.append([_norm(head or ""), _norm(body or ""), [str(c) for c in cites]])
    return json.dumps(rows)


def _word_text(item: Item) -> str:
    """The item as the Word copy writes it: head and body joined by a colon, then the sub lines."""
    text = f"{item.head}: {item.body}" if item.head else item.body
    return _norm(" ".join([text, *item.sub]))


def _edited(item: Item, text: str) -> Item:
    """The item with its body replaced by the reviewed text; head, sub lines and citations stay."""
    body = _norm(text)
    if item.head and body.startswith(f"{item.head}: "):
        body = body[len(item.head) + 2 :]
    elif item.head and body == item.head:
        body = ""
    tail = _norm(" ".join(item.sub))
    if tail and body.endswith(tail):
        body = body[: -len(tail)].strip()
    return item.model_copy(update={"body": body}, deep=True)


def _items_for(section: Section, texts: list[str]) -> list[Item]:
    """The section's items for the reviewed list texts.

    A text equal to an item's Word-copy text keeps that item whole. A text that begins with a remaining
    item's head keeps its head, sub lines and citations and sets the body. Any other text is a new item.
    """
    pool = list(section.items)
    result: list[Item | None] = [None] * len(texts)
    for position, text in enumerate(texts):
        match = next((i for i in pool if _word_text(i) == _norm(text)), None)
        if match is not None:
            pool.remove(match)
            result[position] = match
    for position, text in enumerate(texts):
        if result[position] is not None:
            continue
        match = next((i for i in pool if i.head and _norm(text).startswith(f"{i.head}: ")), None)
        if match is not None:
            pool.remove(match)
            result[position] = _edited(match, text)
        else:
            result[position] = Item(body=text)
    return [item for item in result if item is not None]


def _changed_parts(
    by_id: dict[str | None, Section], sent: dict[str, dict[str, Any]], decided: _Decisions
) -> dict[str, list[str]]:
    """Touched sections whose title, paragraphs, items or deck fields differ from the sent version, with the parts."""
    changed: dict[str, list[str]] = {}
    touched = {*decided.wording, *decided.proposals, *decided.asks, *decided.fields, *decided.items}
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
    by_id = {s.id: s for s in doc.sections}
    decided = _Decisions(plan)
    structure = _accepted_structure(plan)
    deletes = [i.section for i in structure if i.kind == "delete" and i.section]
    touched = [*decided.rewritten(), *decided.asks, *deletes]
    missing = sorted({s for s in touched if s not in by_id})
    for section_id in missing:
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
        words = decided.paragraph_words(section_id)
        if words:
            paragraphs = _paragraphs(words)
            if paragraphs and new.title and _norm(paragraphs[0]) == _norm(new.title):
                paragraphs = paragraphs[1:]  # `review read` stores the heading with the text
            new = new.model_copy(update={"paragraphs": paragraphs}, deep=True)
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
