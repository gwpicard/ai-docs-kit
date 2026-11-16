from collections.abc import Mapping
from typing import Any

from ai_docs_kit.checks.engine import CheckContext, make_finding, register
from ai_docs_kit.model import Finding, Provenance, Remedy, Rule
from ai_docs_kit.model.rules import Tier
from ai_docs_kit.render.marks import ElementMark


def _text(value: Any) -> str | None:
    if value is None or isinstance(value, bool | list | dict):
        return None
    return str(value)


def declared_values(data: Mapping[str, Any] | None) -> list[tuple[str, str | None]]:
    """Return the `(field, text)` pairs a table or chart data block declares."""
    if not isinstance(data, Mapping):
        return []
    columns, rows = data.get("columns"), data.get("rows")
    if isinstance(columns, list) and isinstance(rows, list) and all(isinstance(row, list) for row in rows):
        pairs = [(f"data.columns[{j}]", _text(cell)) for j, cell in enumerate(columns)]
        pairs += [(f"data.rows[{r}][{c}]", _text(cell)) for r, row in enumerate(rows) for c, cell in enumerate(row)]
        return [(field, text) for field, text in pairs if text is not None]
    categories, series = data.get("categories"), data.get("series")
    if isinstance(categories, list) and isinstance(series, list) and all(isinstance(s, Mapping) for s in series):
        out = [(f"data.categories[{i}]", _text(c)) for i, c in enumerate(categories)]
        out = [pair for pair in out if pair[1] is not None]
        for j, entry in enumerate(series):
            values = entry.get("values")
            if not isinstance(values, list):
                continue
            out += [(f"data.series[{j}].values[{i}]", None) for i in range(min(len(categories), len(values)))]
        return out
    return []


def _squash(text: str) -> str:
    return "".join(text.split())


@register("values-visible")
class ValuesVisible:
    tier: Tier = "geometry"

    def run(self, ctx: CheckContext, rule: Rule) -> list[Finding]:
        facts = ctx.facts
        if facts is None:
            return []
        sizes = {page.page: (page.width, page.height) for page in facts.pages}

        def on_page(mark: ElementMark) -> bool:
            if mark.page not in sizes:
                return False
            width, height = sizes[mark.page]
            return 0 <= mark.x + mark.w / 2 <= width and 0 <= mark.y + mark.h / 2 <= height

        findings: list[Finding] = []
        for section in ctx.doc.sections:
            declared = declared_values(section.data) if section.id else []
            if not declared:
                continue
            marks = [
                m
                for m in facts.marks
                if isinstance(m, ElementMark) and m.id == section.id and m.field and m.field.startswith("data.")
            ]
            if not marks:
                continue
            shown = [m for m in marks if on_page(m)]
            for field, text in declared:
                if not any(m.field == field and self._holds(facts, m, text) for m in shown):
                    label = field if text is None else f"{field} ({text})"
                    findings.append(
                        make_finding(
                            rule,
                            ctx,
                            section_id=section.id,
                            role="data",
                            message=f"{label} is not shown on the page",
                            measured={"field": field, "value": text},
                            key=field,
                        )
                    )
        return findings

    @staticmethod
    def _holds(facts: Any, mark: ElementMark, text: str | None) -> bool:
        if text is None:
            return True
        inside = [
            _squash(w.text)
            for w in facts.words
            if w.box.page == mark.page
            and mark.x <= (w.box.x0 + w.box.x1) / 2 <= mark.x + mark.w
            and mark.y <= (w.box.y0 + w.box.y1) / 2 <= mark.y + mark.h
        ]
        return _squash(text) in "".join(inside)


RULES = [
    Rule(
        id="data.values-visible",
        title="Every value a section's data declares is on the page",
        origin="manual",
        strength="hard",
        status="active",
        severity="error",
        tier="geometry",
        check={"kind": "values-visible"},
        remedy=Remedy.model_validate(
            {
                "class": "restructure",
                "hint": "show every declared value: split the data across sections or choose a component that holds it",
            }
        ),
        provenance=Provenance(source={"doc": "PRODUCT.md", "section": "6"}),
    )
]
