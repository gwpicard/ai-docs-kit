"""Fact support and preservation checks for section rewrites."""

import re
from collections.abc import Collection, Mapping, Sequence
from decimal import Decimal, InvalidOperation, localcontext

from ai_docs_kit.agents.gatherer import Fact
from ai_docs_kit.checks.engine import CheckContext, make_finding
from ai_docs_kit.model import Document, Finding, Provenance, Remedy, Rule, Section
from ai_docs_kit.source.parser import CITATION

NUM = re.compile(r"(?<![\w.])[-+]?\d[\d,.]*\d%?|\b\d%?")
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
DATE = re.compile(rf"\b(?:19|20)\d{{2}}\b|\b\d{{1,2}}\s+(?:{MONTHS})\b", re.IGNORECASE)
ENT = re.compile(r"\b[A-Z][a-zA-Z&-]+(?:[ ]+[A-Z][a-zA-Z&-]+)*\b")
SENTENCE_START = re.compile(r"""(?:^|[.!?]["'”’)]*\s+|\*\*[^*\n]+(?:[:.]\*\*|\*\*\s*[:.]|:)\s+)[\s"'“‘(]*$""")
OPENERS = {"A", "An", "The", "In", "On", "At", "By", "For", "From", "To", "With", "As", "After", "Before", "During"}
WORDS = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen twenty"
).split()
WORD_NUMBERS = {word: str(i) for i, word in enumerate(WORDS)}
WORD = re.compile(r"\b(?:" + "|".join(WORDS) + r")\b", re.IGNORECASE)
DOCUMENT_COUNT = re.compile(WORD.pattern + r"(?=\s+(sources?|sections?)\b)", re.IGNORECASE)
CALC = re.compile(r"^\s*calc:\s*(sum|difference|ratio|percentage)\(([^()]*)\)\s*=\s*([-+]?\d[\d,]*(?:\.\d+)?%?)\s*$")
NUMBER = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?%?")


def support_tokens(text: str, *, evidence: bool = False, document_counts: Mapping[str, int] | None = None) -> set[str]:
    """Collect claim tokens, keeping isolated opening names when reading evidence."""
    text = CITATION.sub(" ", text)
    if document_counts is not None:
        # Remove only matching occurrences before sets combine claims or evidence.
        text = DOCUMENT_COUNT.sub(
            lambda match: (
                ""
                if WORD_NUMBERS[match.group().lower()]
                == str(document_counts.get(match.group(1).lower().removesuffix("s")))
                else match.group()
            ),
            text,
        )
    text = WORD.sub(lambda match: WORD_NUMBERS[match.group().lower()], text)
    entities = set()
    for match in ENT.finditer(text):
        words = match.group().split()
        if SENTENCE_START.search(text[: match.start()]):
            if len(words) == 1 and not evidence:
                continue
            if len(words) > 1 and words[0] in OPENERS:
                words = words[1:]
        # A month alone is calendar wording; its year or day is checked separately.
        if len(words) == 1 and words[0] in MONTHS.split("|"):
            continue
        entities.add(" ".join(words).lower())
    return (
        {match.group().replace(",", "") for match in NUM.finditer(text)}
        | {match.group().lower() for match in DATE.finditer(text)}
        | entities
    )


def _fields(section: Section) -> list[str]:
    fields = [
        section.title or "",
        section.source_line or "",
        *section.paragraphs,
    ]
    for item in section.items:
        # Restore punctuated bold boundaries removed when the parser splits a head.
        if item.head and (":" in item.head or item.head.endswith(".") or item.body.startswith((":", "."))):
            fields.append(f"**{item.head}** {item.body}")
        else:
            fields.extend((item.head or "", item.body))
        fields.extend(item.sub)
    return fields


def fact_tokens(section: Section, *, document_counts: Mapping[str, int] | None = None) -> set[str]:
    return set().union(*(support_tokens(value, document_counts=document_counts) for value in _fields(section)))


def fact_number_tokens(fact: Fact) -> set[str]:
    tokens = {token for token in support_tokens(fact.text) if NUMBER.fullmatch(token)}
    if fact.value is not None:
        value = format(fact.value, "f")
        if "." in value:
            value = value.rstrip("0").rstrip(".")
        tokens.add(value)
        if fact.kind == "percent":
            tokens.add(value + "%")
    return tokens


def resolve_numbers(
    section: Section, facts: Sequence[Fact], *, document_counts: Mapping[str, int] | None = None
) -> dict[str, list[str]]:
    return {
        token: sorted(fact.id for fact in facts if fact.id is not None and token in fact_number_tokens(fact))
        for token in fact_tokens(section, document_counts=document_counts)
        if NUMBER.fullmatch(token)
    }


def _calculation(line: str, allowed: set[str]) -> tuple[str, list[str]] | None:
    match = CALC.fullmatch(line)
    if not match:
        return None
    op, raw_operands, raw_result = match.groups()
    operands = [operand.strip().replace(",", "") for operand in raw_operands.split(",")]
    result = raw_result.replace(",", "")
    if (
        not operands
        or any(not NUMBER.fullmatch(x) or x not in allowed for x in operands)
        or (op != "sum" and len(operands) != 2)
        or (op == "percentage") != result.endswith("%")
    ):
        return None
    try:
        values = [Decimal(x.rstrip("%")) for x in operands]
        expected = Decimal(result.rstrip("%"))
        with localcontext() as ctx:
            ctx.prec = 50
            if op == "sum":
                value = sum(values, Decimal(0))
            elif op == "difference":
                value = values[0] - values[1]
            else:
                value = values[0] / values[1]
                if op == "percentage":
                    value *= 100
            places = len(result.rstrip("%").partition(".")[2])
            if value.quantize(Decimal(1).scaleb(-places)) == expected:
                return result, operands
    except (InvalidOperation, ZeroDivisionError):
        pass
    return None


class FactGuard:
    def __init__(
        self,
        evidence: Sequence[str],
        citation_keys: Collection[str] | None = None,
        *,
        facts: Sequence[Fact] = (),
        numbers_from_facts: bool = False,
        exempt: Collection[str] = (),
        document_counts: Mapping[str, int] | None = None,
    ):
        self.document_counts = document_counts
        self.allowed = set().union(
            *(support_tokens(text, evidence=True, document_counts=document_counts) for text in evidence)
        )
        for fact in facts:
            self.allowed.update(support_tokens(fact.text, evidence=True), fact_number_tokens(fact))
        self.facts = facts
        self.numbers_from_facts = numbers_from_facts
        self.exempt = exempt
        self.citation_keys = citation_keys
        self.unsupported: list[str] = []
        self.resolved: dict[str, list[str]] = {}

    def __call__(self, doc: Document, section: Section) -> bool:  # noqa: ARG002 - fixed by the guard protocol
        calculations = [
            calculation
            for line in (section.note or "").splitlines()
            if (calculation := _calculation(line, self.allowed)) is not None
        ]
        derived = {result for result, _ in calculations}
        self.resolved = resolve_numbers(section, self.facts, document_counts=self.document_counts)
        for result, operands in calculations:
            if result in self.resolved and not self.resolved[result]:
                self.resolved[result] = sorted(
                    {
                        fact.id
                        for fact in self.facts
                        if fact.id is not None and any(operand in fact_number_tokens(fact) for operand in operands)
                    }
                )
        unsupported = fact_tokens(section, document_counts=self.document_counts) - self.allowed - derived
        if self.numbers_from_facts:
            unsupported.update(token for token, ids in self.resolved.items() if not ids and token not in self.exempt)
        if self.citation_keys is not None:
            keys = {citation.key for item in section.items for citation in item.citations}
            keys.update(match.group(1) for value in _fields(section) for match in CITATION.finditer(value))
            unsupported.update(f"cite:{key}" for key in keys.difference(self.citation_keys))
        self.unsupported = sorted(unsupported)
        return not self.unsupported


def kept_facts(before: Section, after: Section) -> list[str]:
    return sorted(fact_tokens(before) & fact_tokens(after))


def _rule(rule_id: str, title: str, hint: str) -> Rule:
    return Rule(
        id=rule_id,
        title=title,
        origin="manual",
        strength="hard",
        status="active",
        severity="error",
        tier="source",
        check={"kind": "fact-guard"},
        remedy=Remedy.model_validate({"class": "redraft", "hint": hint}),
        provenance=Provenance(source={"doc": "DESIGN.md", "section": "11.5", "spike": "docs/spikes/S4-repair.md"}),
    )


RULES = [
    _rule("source.fact-support", "Facts are supported", "Remove the token or write [GAP: ...]."),
    _rule("source.facts-kept", "Facts are kept", "Keep the fact; a fact a title cannot hold may move into an item."),
]


def check_rewrite(before: Document, after: Document) -> list[Finding]:
    sections = {section.id: section for section in before.sections if section.id is not None}
    common_evidence = [part for source in before.sources for part in (source.key, source.text)]
    common_evidence.extend(value for value in before.front.values() if isinstance(value, str))
    findings: list[Finding] = []
    for section in after.sections:
        if section.id is None or section.id not in sections:
            continue
        original = sections[section.id]
        keys = {source.key for source in before.sources}
        keys.update(citation.key for item in original.items for citation in item.citations)
        guard = FactGuard([*_fields(original), *common_evidence], keys)
        guard(after, section)
        lost = sorted(fact_tokens(original) - fact_tokens(section))
        for rule, tokens in zip(RULES, (guard.unsupported, lost), strict=True):
            if tokens:
                findings.append(
                    make_finding(
                        rule,
                        CheckContext(after),
                        section_id=section.id,
                        message=f"{rule.title}: {', '.join(tokens)}",
                        measured={"tokens": tokens},
                    )
                )
    return findings
