from typing import Any

from ai_docs_kit.checks.engine import CheckContext, make_finding, register
from ai_docs_kit.facts.layout import LayoutFacts, PlacedWord, centre, contains
from ai_docs_kit.model import Finding, Provenance, Rule
from ai_docs_kit.model.rules import Tier
from ai_docs_kit.render.marks import ElementMark, FitMark

PROVENANCE = Provenance(source={"doc": "DESIGN.md", "section": "10.5"})


def _baseline(word: PlacedWord) -> float:
    return round(word.baseline * 2) / 2


def _cut_to_save_line(words: list[PlacedWord], last: float) -> int:
    on_last = sorted((w for w in words if _baseline(w) == last), key=lambda w: w.box.x0)
    return len(" ".join(w.text for w in on_last)) + 1


def _item_entry(n: int, box: ElementMark, facts: LayoutFacts) -> dict[str, Any]:
    words = [w for w in facts.words if w.role == "item" and contains(box, centre(w.box))]
    baselines = sorted({_baseline(w) for w in words})
    cut = _cut_to_save_line(words, baselines[-1]) if len(baselines) > 1 else None
    return {"n": n, "lines": len(baselines), "cut_to_save_line": cut}


def _items(section_id: str, facts: LayoutFacts) -> list[dict[str, Any]]:
    boxes = [m for m in facts.marks if isinstance(m, ElementMark) and m.role == "item" and m.id == section_id]
    return [_item_entry(n, box, facts) for n, box in enumerate(boxes)]


def _message(mark: FitMark, over: float, items: list[dict[str, Any]]) -> str:
    message = f"{mark.role} frame overflows by {over} pt ({mark.need:.1f} pt needed, {mark.have:.1f} pt available)"
    wrapping = [str(entry["n"]) for entry in items if entry["lines"] > 1]
    if wrapping:
        message += f"; items that wrap: {', '.join(wrapping)}"
    return message


def _finding(rule: Rule, ctx: CheckContext, facts: LayoutFacts, mark: FitMark, nth: int) -> Finding:
    over = round(mark.need - mark.have, 1)
    items = _items(mark.id, facts)
    return make_finding(
        rule,
        ctx,
        message=_message(mark, over, items),
        section_id=mark.id,
        role=mark.role,
        key=str(nth) if nth else None,
        measured={"need": mark.need, "have": mark.have, "over": over, "items": items},
    )


@register("fits")
class TextFits:
    tier: Tier = "geometry"

    def run(self, ctx: CheckContext, rule: Rule) -> list[Finding]:
        facts = ctx.facts
        if facts is None:
            return []
        seen: dict[tuple[str, str], int] = {}
        findings: list[Finding] = []
        for mark in facts.marks:
            if not isinstance(mark, FitMark) or mark.ok:
                continue
            nth = seen.get((mark.id, mark.role), 0)
            seen[(mark.id, mark.role)] = nth + 1
            findings.append(_finding(rule, ctx, facts, mark, nth))
        return findings


RULES: list[Rule] = [
    Rule.model_validate(
        {
            "id": "geo.text-fits",
            "title": "Content fits its fixed frame",
            "origin": "manual",
            "strength": "hard",
            "status": "active",
            "severity": "error",
            "tier": "geometry",
            "scope": {"format": "slides"},
            "check": {"kind": "fits"},
            "remedy": {"class": "redraft", "hint": "cut the items that wrap until the frame fits"},
            "provenance": PROVENANCE,
        }
    ),
]
