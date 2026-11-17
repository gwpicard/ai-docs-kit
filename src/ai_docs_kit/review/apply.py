"""`review apply`: put a decided review plan into the working file."""

import argparse
import json
import re
import sys
from pathlib import Path

from ai_docs_kit.model import Document, Patch, PatchOp, Section
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


def _sent_paragraphs(path: Path, number: int) -> dict[str, str]:
    composition = path.parent / f"{path.stem}.versions" / f"v{number}" / "composition.json"
    try:
        data = json.loads(composition.read_text(encoding="utf-8"))
        return {
            s["id"]: "\n\n".join(s["props"].get("paragraphs", []))
            for s in data["sections"]
            if isinstance(s.get("id"), str)
        }
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ApplyError(f"{composition}: cannot read the sent version: {' '.join(str(error).split())}", 2) from error


def _decisions(plan: ReviewPlan) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """The wording, proposals and redraft asks the person accepted, by section id."""
    wording: dict[str, str] = {}
    proposals: dict[str, str] = {}
    asks: dict[str, str] = {}
    for section_id, item in plan.sections.items():
        if item.wording:
            wording[section_id] = item.wording
        for comment in item.confirm:
            if comment.accepted is not True:
                continue
            if comment.action == "apply" and comment.proposal:
                proposals[section_id] = comment.proposal
            elif comment.action == "redraft":
                asks[section_id] = comment.ask or comment.text
    return wording, proposals, asks


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


def _replace(old: Section, words: str) -> PatchOp:
    new = old.model_copy(update={"paragraphs": _paragraphs(words), "owner": "human"}, deep=True)
    return PatchOp(op="replace_section", section_id=old.id or "", value=new)


def apply_plan(path: Path, plan_path: Path) -> dict[str, list[str]]:
    plan = _load_plan(plan_path)
    doc = _load_doc(path)
    by_id = {s.id: s for s in doc.sections if s.id}
    wording, proposals, asks = _decisions(plan)
    structure = _accepted_structure(plan)
    deletes = [i.section for i in structure if i.kind == "delete" and i.section]
    touched = [*wording, *proposals, *asks, *deletes]
    unknown = sorted({s for s in touched if s not in by_id})
    if unknown:
        raise ApplyError(f"the plan names sections the working file does not have: {', '.join(unknown)}")
    sent = _sent_paragraphs(path, plan.sent_version)
    changed = sorted(
        {
            s
            for s in touched
            if _norm("\n\n".join(by_id[s].paragraphs)) != _norm(sent.get(s, "\n\n".join(by_id[s].paragraphs)))
        }
    )
    if changed:
        raise ApplyError(
            f"the working file changed since version v{plan.sent_version} was sent in: {', '.join(changed)}; "
            "read the review copy again or settle those sections first"
        )
    ops: list[PatchOp] = []
    applied: list[str] = []
    for section_id in [*wording, *(s for s in proposals if s not in wording)]:
        ops.append(_replace(by_id[section_id], proposals.get(section_id) or wording[section_id]))
        applied.append(section_id)
    redrafted = [s for s in asks if s not in deletes]
    ops.extend(PatchOp(op="set_attr", section_id=s, fields={"name": "redraft", "value": asks[s]}) for s in redrafted)
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
    return {"applied": applied, "redrafted": redrafted, "moved": moved, "deleted": deletes}


def _simulate(order: list[str], ops: list[PatchOp]) -> list[str]:
    current = list(order)
    for op in ops:
        current.remove(op.section_id)
        current.insert(current.index(op.after_id or "") + 1, op.section_id)
    return current


def run_apply(args: argparse.Namespace) -> int:
    try:
        touched = apply_plan(args.file, args.plan)
    except ApplyError as error:
        print(error, file=sys.stderr)
        return error.code
    except (OSError, ValueError) as error:
        print(" ".join(str(error).split()), file=sys.stderr)
        return 2
    print(f"applied the plan to {args.file}")
    print("touched " + json.dumps(touched))
    return 0
