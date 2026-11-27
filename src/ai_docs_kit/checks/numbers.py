"""Check section figures against stored facts, sources and front matter."""

import re
from collections.abc import Iterator, Sequence
from decimal import Decimal

from ai_docs_kit.agents.gatherer import Fact
from ai_docs_kit.checks.engine import CheckContext, finding_key, make_finding, register
from ai_docs_kit.loop.guards import NUM, NUMBER, fact_number_tokens
from ai_docs_kit.model import Citation, Finding, Provenance, Remedy, Rule, Section
from ai_docs_kit.model.rules import Tier
from ai_docs_kit.source.parser import CITATION

YEAR = re.compile(r"(?:19|20)\d{2}")


def written_numbers(text: str) -> list[str]:
    return [
        token for match in NUM.finditer(CITATION.sub(" ", text)) if not YEAR.fullmatch(token := match.group().strip())
    ]


def fact_numbers(fact: Fact) -> list[tuple[Decimal, bool]]:
    return [
        (abs(Decimal(token.replace(",", "").rstrip("%"))), token.endswith("%"))
        for token in fact_number_tokens(fact)
        if NUMBER.fullmatch(token)
    ]


def within_rounding(written: str, value: Decimal) -> bool:
    number = written.replace(",", "").rstrip("%")
    if not NUMBER.fullmatch(written):
        return False
    places = len(number.partition(".")[2])
    return abs(abs(Decimal(number)) - abs(value)) <= Decimal(5) * Decimal(10) ** (-places - 1)


def cited_facts(facts: Sequence[Fact], citation: Citation) -> list[Fact]:
    matching = [fact for fact in facts if fact.source_key == citation.key]
    located = [fact for fact in matching if citation.locator and fact.locator == citation.locator]
    return located or matching


def _table_cells(section: Section) -> Iterator[tuple[str, str]]:
    data = section.data or {}
    columns = data.get("columns")
    if isinstance(columns, list):
        for column, cell in enumerate(columns):
            yield f"data.columns[{column}]", str(cell)
    rows = data.get("rows")
    if isinstance(rows, list):
        for row_index, row in enumerate(rows):
            if isinstance(row, list):
                for column, cell in enumerate(row):
                    yield f"data.rows[{row_index}][{column}]", str(cell)


def _claims(section: Section) -> Iterator[tuple[str | int, Sequence[str], list[Citation]]]:
    for index, item in enumerate(section.items):
        yield index, (item.head or "", item.body, *item.sub), item.citations
    for field, text in (
        ("title", section.title or ""),
        ("source_line", section.source_line or ""),
        *((f"paragraphs[{index}]", text) for index, text in enumerate(section.paragraphs)),
        *_table_cells(section),
    ):
        citations = [
            Citation(key=match.group(1), locator=match.group(2).strip() if match.group(2) else None)
            for match in CITATION.finditer(text)
        ]
        yield field, (text,), citations


@register("number-in-source")
class NumberInSource:
    tier: Tier = "source"

    def run(self, ctx: CheckContext, rule: Rule) -> list[Finding]:
        if ctx.source_facts is None:
            return []
        facts = [*ctx.source_facts, *(Fact(text=source.text, source_key=source.key) for source in ctx.doc.sources)]
        front = [Fact(text=value, source_key="") for value in ctx.doc.front.values() if isinstance(value, str)]
        findings = []
        for index, section in enumerate(ctx.doc.sections):
            for field, texts, references in _claims(section):
                candidates = (
                    [fact for citation in references for fact in cited_facts(facts, citation)] if references else facts
                )
                candidates = [*candidates, *front]
                values = [pair for fact in candidates for pair in fact_numbers(fact)]
                citations = [f"{c.key} {c.locator}" if c.locator else c.key for c in references]
                for text in texts:
                    for number in written_numbers(text):
                        if any(
                            percent == number.endswith("%") and within_rounding(number, value)
                            for value, percent in values
                        ):
                            continue
                        findings.append(
                            make_finding(
                                rule,
                                ctx,
                                section_id=section.id,
                                message=(
                                    f"{number} is not in the cited source {citations}"
                                    if citations
                                    else f"{number} is not in the stored facts, sources or front matter"
                                ),
                                measured={
                                    "number": number,
                                    "item" if isinstance(field, int) else "field": field,
                                    "citations": citations,
                                },
                                key=finding_key(section, index, f"{field}:{number}"),
                            )
                        )
        return findings


RULES = [
    Rule(
        id="source.number-in-source",
        title="The cited source holds every quoted number",
        origin="manual",
        strength="hard",
        status="active",
        severity="error",
        tier="source",
        check={"kind": "number-in-source"},
        remedy=Remedy.model_validate(
            {
                "class": "redraft",
                "hint": "use the number as the cited source states it, or cite the source that holds it",
            }
        ),
        provenance=Provenance(source={"doc": "PRODUCT.md", "section": "6"}),
    )
]
