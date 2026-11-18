import re

from ai_docs_kit.checks.engine import CheckContext, finding_key, make_finding, register
from ai_docs_kit.checks.source import PROVENANCE
from ai_docs_kit.model import Finding, Remedy, Rule, Section
from ai_docs_kit.model.rules import Tier

NUM = re.compile(r"(?<![\w.])[-+]?\d[\d,.\s]*\d%?|\b\d%?\b")


def _numbers(section: Section) -> list[str]:
    return [
        match.group().strip()
        for item in section.items
        if not item.citations
        for text in (item.head or "", item.body, *item.sub)
        for match in NUM.finditer(text)
    ]


@register("uncited-figure")
class UncitedFigure:
    tier: Tier = "source"

    def run(self, ctx: CheckContext, rule: Rule) -> list[Finding]:
        if not ctx.final:
            return []
        return [
            make_finding(
                rule,
                ctx,
                message=f"figure {numbers[0]} has no citation",
                section_id=section.id,
                measured={"numbers": numbers},
                severity="error",
                key=finding_key(section, index),
            )
            for index, section in enumerate(ctx.doc.sections)
            if (numbers := _numbers(section))
        ]


RULES: list[Rule] = [
    Rule(
        id="source.uncited-figure",
        title="Every item figure has a citation",
        origin="manual",
        strength="hard",
        status="active",
        severity="error",
        tier="source",
        check={"kind": "uncited-figure"},
        remedy=Remedy.model_validate({"class": "redraft", "hint": "cite a source for the figure"}),
        provenance=PROVENANCE,
    ),
]
