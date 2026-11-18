"""`review read`: compare a Word review copy with the version it was built from and write the plan."""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from ai_docs_kit.review.apply import add_apply_command, run_apply
from ai_docs_kit.review.plan import (
    CommentItem,
    Emphasis,
    ReviewPlan,
    SectionPlan,
    StructureItem,
    Warning,
)
from ai_docs_kit.review.pptx_read import DeckText, read_deck
from ai_docs_kit.review.word_read import WordText, read_word

PLAN_NAME = "review-plan.json"
SUMMARY_ITEMS = 6


class ReadError(Exception):
    def __init__(self, message: str, code: int = 2) -> None:
        super().__init__(message)
        self.code = code


def add_review_commands(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    review = subparsers.add_parser("review", help="read a review copy into a plan")
    commands = review.add_subparsers(dest="review_command", required=True)
    read = commands.add_parser("read", help="read a Word or PowerPoint review copy into a review plan")
    read.add_argument("copy", type=Path, help="the review copy (.docx or .pptx), kept beside the working file")
    add_apply_command(commands)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _versions_folder(copy: Path) -> Path:
    """The `<working file>.versions` folder beside the copy; the longest stem the copy's name starts with."""
    folders = sorted(p for p in copy.parent.glob("*.versions") if p.is_dir())
    named = [p for p in folders if copy.stem == p.name[: -len(".versions")] or _prefix(copy.stem, p)]
    chosen = max(named, key=lambda p: len(p.name), default=None)
    if chosen is None and len(folders) == 1:
        chosen = folders[0]
    if chosen is None:
        raise ReadError(f"{copy}: no working file with versions beside it")
    return chosen


def _prefix(stem: str, folder: Path) -> bool:
    base = folder.name[: -len(".versions")]
    return stem.startswith(base) and not stem[len(base) : len(base) + 1].isalnum()


def _version_for(folder: Path, copy: Path) -> tuple[int, Path, Warning | None]:
    """The version a copy was built from, named by its property; else the latest version, with a warning."""
    from ai_docs_kit.store import load_version
    from ai_docs_kit.store.stamp import read_version_property

    found: dict[int, Path] = {}
    for directory in folder.glob("v*"):
        try:
            found[load_version(directory).number] = directory
        except (OSError, ValueError):
            continue
    named = read_version_property(copy)
    if named is not None and named in found:
        return named, found[named], None
    if not found:
        raise ReadError(f"{folder.name[: -len('.versions')]}: no version to compare with")
    number = max(found)
    why = "has no version property" if named is None else f"names version v{named}, which no longer exists"
    warning = Warning(
        code="version_assumed", message=f"The copy {why}; it was compared with the latest version, v{number}."
    )
    return number, found[number], warning


def _text(parts: WordText, section: str) -> str:
    return "\n\n".join(parts.paragraphs.get(section, []))


def _items(parts: WordText, section: str) -> list[str]:
    return [_norm(i) for i in parts.items.get(section, [])]


def _present(parts: WordText, section: str) -> bool:
    return section in parts.order


def build_plan(sent: WordText, copy: WordText, number: int, name: str) -> ReviewPlan:
    sections: dict[str, SectionPlan] = {}
    structure: list[StructureItem] = []
    changed = False
    for section in sent.order:
        before, after = _text(sent, section), _text(copy, section)
        listed_before, listed_after = _items(sent, section), _items(copy, section)
        item = SectionPlan(wording=None, owner=None)
        if _present(copy, section) and after and _norm(before) != _norm(after):
            item.wording, item.owner = after, "human"
        elif (before or listed_before) and not after and not listed_after:
            structure.append(StructureItem(kind="delete", section=section, text=before or "\n".join(listed_before)))
        if _present(copy, section) and (after or listed_after) and listed_before != listed_after:
            item.items, item.owner = list(copy.items.get(section, [])), "human"
        seen = Counter((e[0], _norm(e[1]), e[2]) for e in sent.emphasis.get(section, []))
        for kind, text, value in copy.emphasis.get(section, []):
            key = (kind, _norm(text), value)
            if seen[key] > 0:
                seen[key] -= 1
            else:
                item.emphasis.append(Emphasis(kind=kind, text=_norm(text), value=value))  # type: ignore[arg-type]
        sections[section] = item
        changed = changed or bool(item.wording or item.emphasis or item.items is not None)
    placed = [s for s in sent.order if _present(copy, s)]
    order = [s for s in copy.order if s in placed]
    if order != placed:
        structure.append(
            StructureItem(kind="reorder", text="The sections now run in this order: " + ", ".join(order), order=order)
        )
    known = Counter(text for _, text in sent.unplaced)
    for follows, text in copy.unplaced:
        if known[text] > 0:
            known[text] -= 1
        else:
            structure.append(StructureItem(kind="unplaced", text=text, after=follows))
    for owner, comment in copy.comments:
        anchor = _norm("".join(comment.anchor))
        spans = [name for name in comment.spans if name in sections]
        if owner in sections:
            spans = spans or [owner]
            for name in spans:
                note = CommentItem(author=comment.author, text=comment.text, anchor=anchor, spans=spans)
                sections[name].confirm.append(note)
        else:
            structure.append(
                StructureItem(
                    kind="unplaced",
                    text=f"{comment.text} (on: {anchor})" if anchor else comment.text,
                    author=comment.author,
                )
            )
    changed = changed or bool(structure) or any(s.confirm for s in sections.values())
    return _plan(number, name, sections, structure, changed)


def _plan(
    number: int, name: str, sections: dict[str, SectionPlan], structure: list[StructureItem], changed: bool
) -> ReviewPlan:
    warnings = []
    if not changed:
        warnings.append(
            Warning(
                code="tracking_warning",
                message="The copy matches its version: no edits, comments or formatting changes were found."
                " Track changes may have been off.",
            )
        )
    return ReviewPlan(version=number, review_copy=name, sections=sections, confirm=structure, warnings=warnings)


def build_deck_plan(sent: DeckText, copy: DeckText, number: int, name: str) -> ReviewPlan:
    sections: dict[str, SectionPlan] = {}
    structure: list[StructureItem] = []
    for section in sent.order:
        item = SectionPlan(wording=None, owner=None)
        present = section in copy.slide_of
        words = " ".join(sent.fields[section].values())
        if not present:
            structure.append(StructureItem(kind="delete", section=section, text=words))
        for path, before in sent.fields[section].items():
            after = copy.fields.get(section, {}).get(path)
            if after is None:
                continue
            moved = _norm(before) != _norm(after)
            if moved and after:
                item.fields[path] = after
                item.owner = "human"
            known = Counter((e[0], _norm(e[1]), e[2]) for e in sent.formats[(section, path)])
            formats = {(kind, value) for kind, _, value in known}
            for kind, text, value in copy.formats.get((section, path), []):
                key = (kind, _norm(text), value)
                if known[key] > 0:
                    known[key] -= 1
                elif not moved or (kind, value) not in formats:
                    item.emphasis.append(Emphasis(kind=kind, text=_norm(text), value=value))  # type: ignore[arg-type]
        for path, after in copy.fields.get(section, {}).items():
            if path not in sent.fields[section] and after:
                structure.append(StructureItem(kind="unplaced", text=f"{section}/{path}: {after}", after=section))
        sections[section] = item
    placed = [s for s in sent.order if s in copy.slide_of]
    order = [s for s in copy.order if s in placed]
    if order != placed:
        structure.append(
            StructureItem(kind="reorder", text="The slides now run in this order: " + ", ".join(order), order=order)
        )
    known_text = Counter(text for _, text in sent.unplaced)
    for follows, text in copy.unplaced:
        if known_text[text] > 0:
            known_text[text] -= 1
        else:
            structure.append(StructureItem(kind="unplaced", text=text, after=follows))
    for owner, comment in copy.comments:
        anchor = _norm("".join(comment.anchor))
        if owner in sections:
            number_in_sent = sent.slide_of[owner]
            sections[owner].confirm.append(
                CommentItem(
                    author=comment.author,
                    text=comment.text,
                    anchor=anchor,
                    slide=number_in_sent,
                    shape=comment.shape,
                    id=comment.id,
                    reply_to=comment.reply_to,
                )
            )
        else:
            structure.append(
                StructureItem(
                    kind="unplaced",
                    text=f"{comment.text} (on slide {comment.slide})",
                    author=comment.author,
                )
            )
    changed = bool(structure) or any(s.fields or s.emphasis or s.confirm for s in sections.values())
    return _plan(number, name, sections, structure, changed)


def summary(plan: ReviewPlan, path: Path) -> list[str]:
    lines = [f"review copy {plan.review_copy} against version v{plan.version}"]
    for section, item in plan.sections.items():
        parts = []
        if item.wording or item.fields:
            parts.append("wording changed")
        if item.items is not None:
            parts.append("list items changed")
        if item.confirm:
            parts.append(f"{len(item.confirm)} comment(s)")
        if item.emphasis:
            parts.append(f"{len(item.emphasis)} emphasis hint(s)")
        if parts:
            lines.append(f"  {section}: {', '.join(parts)}")
    kinds = Counter(c.kind for c in plan.confirm)
    for kind, count in sorted(kinds.items()):
        lines.append(f"  {count} {kind} item(s) to confirm")
    lines += [f"  warning {w.code}: {w.message}" for w in plan.warnings]
    if len(lines) > 20:
        lines = [*lines[:19], f"  and {len(lines) - 19} more lines in the plan"]
    return [*lines, f"plan: {path}"]


def run_review(args: argparse.Namespace) -> int:
    if args.review_command == "apply":
        return run_apply(args)
    copy: Path = args.copy
    try:
        if not copy.is_file():
            raise ReadError(f"{copy}: no such review copy")
        folder = _versions_folder(copy)
        number, directory, assumed = _version_for(folder, copy)
        deck = copy.suffix.lower() == ".pptx"
        sent_file = directory / f"{folder.name[: -len('.versions')]}{'.pptx' if deck else '.docx'}"
        if not sent_file.is_file():
            raise ReadError(f"{sent_file}: the version has no {'PowerPoint' if deck else 'Word'} copy")
        if deck:
            sent_deck = read_deck(sent_file)
            plan = build_deck_plan(sent_deck, read_deck(copy, set(sent_deck.order)), number, copy.name)
        else:
            sent = read_word(sent_file)
            plan = build_plan(sent, read_word(copy, set(sent.order)), number, copy.name)
        if assumed:
            plan.warnings.append(assumed)
        path = directory / PLAN_NAME
        path.write_text(json.dumps(plan.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except ReadError as error:
        print(error, file=sys.stderr)
        return error.code
    except (OSError, ValueError) as error:
        print(" ".join(str(error).split()), file=sys.stderr)
        return 2
    print("\n".join(summary(plan, path)))
    return 0
