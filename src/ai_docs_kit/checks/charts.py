import re
from math import hypot
from typing import Any

from ai_docs_kit.checks.engine import CheckContext, make_finding, register
from ai_docs_kit.model import Box, Finding, Provenance, Remedy, Rule
from ai_docs_kit.model.rules import Tier
from ai_docs_kit.render.marks import ElementMark


def _box(mark: ElementMark) -> Box:
    return Box(x=mark.x, y=mark.y, w=mark.w, h=mark.h)


def _gaps(a: ElementMark, b: ElementMark) -> tuple[float, float]:
    return (
        max(0, a.x - b.x - b.w, b.x - a.x - a.w),
        max(0, a.y - b.y - b.h, b.y - a.y - a.h),
    )


def _union(group: list[ElementMark]) -> ElementMark:
    x0 = min(m.x for m in group)
    y0 = min(m.y for m in group)
    first = group[0]
    return first.model_copy(
        update={"x": x0, "y": y0, "w": max(m.x + m.w for m in group) - x0, "h": max(m.y + m.h for m in group) - y0}
    )


def _by_field(labels: list[ElementMark], marks: list[ElementMark]) -> list[tuple[ElementMark, ElementMark]] | None:
    """Pair each label with the marks of its category, read from the `field` paths; None when they do not say."""
    groups: dict[str, list[ElementMark]] = {}
    for mark in marks:
        found = re.search(r"values\[(\d+)\]$", mark.field or "")
        if found is None:
            return None
        groups.setdefault(found.group(1), []).append(mark)
    pairs = []
    for label in labels:
        found = re.fullmatch(r"data\.categories\[(\d+)\]", label.field or "")
        if found is None or found.group(1) not in groups:
            return None
        pairs.append((label, _union(groups[found.group(1)])))
    return pairs


def _labels(
    ctx: CheckContext, rule: Rule, labels: list[ElementMark], marks: list[ElementMark], data: dict[str, Any] | None
) -> list[Finding]:
    findings = []
    tolerance = float(rule.check["tolerance_pt"])
    by_field = _by_field(labels, marks)
    if by_field is not None:
        pairs = by_field
    elif (
        data is not None
        and len(labels) == len(data.get("categories", []))
        and len(marks) == len(labels) * len(data.get("series", []))
    ):
        per = len(data["series"])
        pairs = [(label, _union(marks[i * per : (i + 1) * per])) for i, label in enumerate(labels)]
    else:
        pairs = list(zip(labels, marks, strict=False))
    for index, (label, mark) in enumerate(pairs):
        dx, dy = _gaps(label, mark)
        if dx > 2 * tolerance and dy > 2 * tolerance:
            findings.append(
                make_finding(
                    rule,
                    ctx,
                    section_id=label.id,
                    role=label.role,
                    page=label.page,
                    region=_box(label),
                    message=f"chart label {index} is away from its mark",
                    measured={"label": index, "off_pt": round(hypot(dx, dy), 1)},
                    key=f"label:{index}",
                )
            )
    return findings


def _data(ctx: CheckContext, section_id: str) -> dict[str, Any] | None:
    if ctx.composition is None:
        return None
    section = next((s for s in ctx.composition.sections if s.id == section_id), None)
    if section is None:
        return None
    data = section.content.get("data")
    if isinstance(data, dict) and data.get("type") in ("bar", "column"):
        return data
    spec = section.content.get("chart")
    if isinstance(spec, dict) and spec.get("type") in ("bar", "column"):
        return {
            "type": spec["type"],
            "categories": spec["categories"],
            "series": [{"values": s["values"]} for s in spec["series"]],
        }
    return None


def _lengths(ctx: CheckContext, rule: Rule, marks: list[ElementMark], data: dict[str, Any]) -> list[Finding]:
    series = data.get("series", [])
    values = [
        max(0, s.get("values", [])[i] if i < len(s.get("values", [])) else 0)
        for i, _ in enumerate(data.get("categories", []))
        for s in series
    ]
    if not values or max(values) == 0 or not marks:
        return []
    lengths = [mark.w if data["type"] == "bar" else mark.h for mark in marks]
    scale = max(lengths) / max(values)
    tolerance = float(rule.check["length_tolerance_pt"])
    findings = []
    for index, (mark, value, length) in enumerate(zip(marks, values, lengths, strict=False)):
        expected = value * scale
        if abs(length - expected) > tolerance:
            findings.append(
                make_finding(
                    rule,
                    ctx,
                    section_id=mark.id,
                    role=mark.role,
                    page=mark.page,
                    region=_box(mark),
                    message=f"chart mark {index} length does not match its value",
                    measured={"mark": index, "value": value, "length_pt": length, "expected_pt": expected},
                    key=f"mark:{index}",
                )
            )
    return findings


@register("chart-labels")
class ChartLabels:
    tier: Tier = "geometry"

    def run(self, ctx: CheckContext, rule: Rule) -> list[Finding]:
        if ctx.facts is None:
            return []
        groups: dict[str, dict[str, list[ElementMark]]] = {}
        for mark in ctx.facts.marks:
            if isinstance(mark, ElementMark) and mark.role in ("chart-label", "chart-mark"):
                groups.setdefault(mark.id, {"chart-label": [], "chart-mark": []})[mark.role].append(mark)
        findings: list[Finding] = []
        for section_id, group in groups.items():
            marks = group["chart-mark"]
            data = _data(ctx, section_id)
            findings.extend(_labels(ctx, rule, group["chart-label"], marks, data))
            if data is not None:
                findings.extend(_lengths(ctx, rule, marks, data))
        return findings


RULES = [
    Rule(
        id="geo.chart-labels",
        title="Chart labels sit by their marks and bars match their values",
        origin="manual",
        strength="hard",
        status="active",
        severity="error",
        tier="geometry",
        check={"kind": "chart-labels", "tolerance_pt": 4, "length_tolerance_pt": 1},
        remedy=Remedy.model_validate({"class": "engine", "hint": "correct the chart layout and mark lengths"}),
        provenance=Provenance(source={"doc": "DESIGN.md", "section": "10.5"}),
    )
]
