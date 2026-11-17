import re

from ai_docs_kit.checks.dsl import _texts
from ai_docs_kit.checks.engine import CheckContext, make_finding, register
from ai_docs_kit.checks.source import PROVENANCE
from ai_docs_kit.model import Finding, Remedy, Rule, Section
from ai_docs_kit.model.rules import Tier
from ai_docs_kit.theme.voice import Term, load_voice


def _term_pattern(term: str) -> str:
    """Word boundaries apply only at an edge that is a word character."""
    start = r"\b" if re.match(r"\w", term) else ""
    end = r"\b" if re.search(r"\w$", term) else ""
    return start + re.escape(term) + end


def _field_finding(ctx: CheckContext, rule: Rule, section: Section, field: str, banned: list[str]) -> Finding | None:
    terms = sorted(
        {
            term
            for term in banned
            if term.strip()
            and any(re.search(_term_pattern(term), text, re.IGNORECASE) for text in _texts(section, field))
        }
    )
    if not terms:
        return None
    names = ", ".join(f'"{term}"' for term in terms)
    return make_finding(
        rule,
        ctx,
        message=f"banned term {names} in {field}",
        section_id=section.id,
        role=field,
        measured={"field": field, "terms": terms},
    )


@register("banned-terms")
class BannedTerms:
    tier: Tier = "source"

    def run(self, ctx: CheckContext, rule: Rule) -> list[Finding]:
        if ctx.theme is None:
            return []
        banned = load_voice(ctx.theme).banned
        return [
            finding
            for section in ctx.doc.sections
            for field in ("title", "items", "paragraphs")
            if (finding := _field_finding(ctx, rule, section, field, banned)) is not None
        ]


def _terminology_finding(
    ctx: CheckContext, rule: Rule, section: Section, field: str, terminology: list[Term]
) -> Finding | None:
    matches = sorted(
        (avoid, term.preferred)
        for term in terminology
        for avoid in term.avoid
        if avoid.strip()
        and any(re.search(_term_pattern(avoid), text, re.IGNORECASE) for text in _texts(section, field))
    )
    if not matches:
        return None
    avoided = sorted({avoid for avoid, _ in matches})
    preferred = sorted({word for _, word in matches})
    advice = "; ".join(f'use "{word}", not "{avoid}"' for avoid, word in matches)
    return make_finding(
        rule,
        ctx,
        message=advice,
        section_id=section.id,
        role=field,
        measured={"field": field, "avoid": avoided, "preferred": preferred},
    )


@register("terminology-drift")
class TerminologyDrift:
    tier: Tier = "source"

    def run(self, ctx: CheckContext, rule: Rule) -> list[Finding]:
        if ctx.theme is None:
            return []
        terminology = load_voice(ctx.theme).terminology
        return [
            finding
            for section in ctx.doc.sections
            for field in ("title", "items", "paragraphs")
            if (finding := _terminology_finding(ctx, rule, section, field, terminology)) is not None
        ]


RULES: list[Rule] = [
    Rule(
        id="source.title-label",
        title="A title is a label, not a question or a teaser",
        origin="manual",
        strength="hard",
        status="active",
        severity="error",
        tier="source",
        check={"kind": "text-pattern", "field": "title", "regex": r"(\?|\.\.\.|…)\s*$", "must_not_match": True},
        remedy=Remedy.model_validate(
            {"class": "redraft", "hint": "rewrite the title as a label that names the finding"}
        ),
        provenance=PROVENANCE,
    ),
    Rule(
        id="source.banned-terms",
        title="Text uses no word the theme's voice bans",
        origin="manual",
        strength="hard",
        status="active",
        severity="error",
        tier="source",
        check={"kind": "banned-terms"},
        remedy=Remedy.model_validate({"class": "redraft", "hint": "replace the banned word with a plain one"}),
        provenance=PROVENANCE,
    ),
    Rule(
        id="source.terminology-drift",
        title="Text uses the theme's preferred word for each concept",
        origin="manual",
        strength="soft",
        status="active",
        severity="warning",
        tier="source",
        check={"kind": "terminology-drift"},
        remedy=Remedy.model_validate({"class": "redraft", "hint": "use the preferred word"}),
        provenance=PROVENANCE,
    ),
]
