import re

from ai_docs_kit.checks.dsl import _texts
from ai_docs_kit.checks.engine import CheckContext, finding_key, make_finding, register
from ai_docs_kit.checks.source import PROVENANCE
from ai_docs_kit.model import Finding, Remedy, Rule, Section
from ai_docs_kit.model.rules import Tier
from ai_docs_kit.theme import Theme, ThemeError
from ai_docs_kit.theme.voice import Term, Voice, load_voice


def _voice(theme: Theme) -> Voice:
    """The theme's voice, or an empty one when the file is refused (`load_theme` reports that first)."""
    try:
        return load_voice(theme)
    except ThemeError:
        return Voice()


# Text the audience reads or hears; `note` and `source_line` are exempt.
VOICE_FIELDS = ("title", "items", "paragraphs", "spoken")
QUOTED = re.compile(r""""([^"]+)"|“([^”]+)”|(?<!\w)'((?:[^']|'(?=\w))+)'(?!\w)|‘((?:[^’]|’(?=\w))+)’(?!\w)""")


def _without_source_quotes(text: str, sources: list[str]) -> str:
    """Mask only complete quotations supported by source wording, keeping other occurrences."""

    def replace(match: re.Match[str]) -> str:
        quotation = " ".join(next(group for group in match.groups() if group is not None).split())
        if quotation and any(re.search(_term_pattern(quotation), source) for source in sources):
            return " " * len(match.group())
        return match.group()

    return QUOTED.sub(replace, text)


def _term_pattern(term: str) -> str:
    """Word boundaries apply only at an edge that is a word character; padding is ignored."""
    term = term.strip()
    start = r"\b" if re.match(r"\w", term) else ""
    end = r"\b" if re.search(r"\w$", term) else ""
    return start + re.escape(term) + end


def _hit(term: str, texts: list[str]) -> bool:
    """Return whether a non-blank term appears in any of the texts, ignoring case."""
    return bool(term.strip()) and any(re.search(_term_pattern(term), text, re.IGNORECASE) for text in texts)


def _field_finding(
    ctx: CheckContext, rule: Rule, section: Section, field: str, banned: list[str], index: int, sources: list[str]
) -> Finding | None:
    texts = _texts(section, field)
    if field == "items":
        # A bold head is part of its bullet, so a quotation can close in the body.
        texts = [
            text
            for item in section.items
            for text in [" ".join(part for part in (item.head, item.body) if part), *item.sub]
        ]
    texts = [_without_source_quotes(text, sources) for text in texts]
    terms = sorted({term for term in banned if _hit(term, texts)})
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
        key=finding_key(section, index),
    )


@register("banned-terms")
class BannedTerms:
    tier: Tier = "source"

    def run(self, ctx: CheckContext, rule: Rule) -> list[Finding]:
        if ctx.theme is None:
            return []
        banned = _voice(ctx.theme).banned
        keys = {source.key for source in ctx.doc.sources}
        sources = [" ".join(source.text.split()) for source in ctx.doc.sources]
        sources.extend(" ".join(fact.text.split()) for fact in ctx.source_facts or [] if fact.source_key in keys)
        return [
            finding
            for index, section in enumerate(ctx.doc.sections)
            for field in VOICE_FIELDS
            if (finding := _field_finding(ctx, rule, section, field, banned, index, sources)) is not None
        ]


def _terminology_finding(
    ctx: CheckContext, rule: Rule, section: Section, field: str, terminology: list[Term], index: int
) -> Finding | None:
    texts = _texts(section, field)
    matches = sorted((avoid, term.preferred) for term in terminology for avoid in term.avoid if _hit(avoid, texts))
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
        key=finding_key(section, index),
    )


@register("terminology-drift")
class TerminologyDrift:
    tier: Tier = "source"

    def run(self, ctx: CheckContext, rule: Rule) -> list[Finding]:
        if ctx.theme is None:
            return []
        terminology = _voice(ctx.theme).terminology
        return [
            finding
            for index, section in enumerate(ctx.doc.sections)
            for field in VOICE_FIELDS
            if (finding := _terminology_finding(ctx, rule, section, field, terminology, index)) is not None
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
