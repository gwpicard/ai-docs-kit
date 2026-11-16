"""Source marks: the numbers drawn on a rendered page, with their boxes and supporting facts."""

import re
from collections import Counter
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel

from ai_docs_kit.agents.gatherer import Fact
from ai_docs_kit.checks.numbers import cited_facts
from ai_docs_kit.facts.layout import LayoutFacts, centre, contains
from ai_docs_kit.loop.guards import NUM, NUMBER, fact_number_tokens, support_tokens
from ai_docs_kit.model.source import Citation
from ai_docs_kit.render.compose import ComposedSection, Composition
from ai_docs_kit.render.marks import ElementMark

PART = re.compile(r"([A-Za-z_]\w*)|\[(\d+)\]")
ITEM = re.compile(r"items\[(\d+)\](?:\.(head|body)|\.sub\[(\d+)\])?")


class SourceMark(BaseModel):
    section: str
    field: str
    text: str
    token: str
    cited: bool
    facts: list[str]
    page: int
    x: float
    y: float
    w: float
    h: float


def _written(value: Any) -> str | None:
    if isinstance(value, str | int | float) and not isinstance(value, bool):
        return str(value)
    return None


def _at(value: Any, parts: Sequence[tuple[str, str]]) -> Any:
    for name, index in parts:
        try:
            value = value[int(index)] if index else value[name]
        except (KeyError, IndexError, TypeError):
            return None
    return value


def _item_text(section: ComposedSection, match: re.Match[str]) -> str | None:
    items = section.props.get("items", [])
    i = int(match.group(1))
    if i >= len(items):
        return None
    item = items[i]
    if match.group(3) is not None:
        sub = item.get("sub", [])
        j = int(match.group(3))
        return _written(sub[j]) if j < len(sub) else None
    if match.group(2) is not None:
        return _written(item.get(match.group(2), ""))
    return f"{item.get('head', '')} {item.get('body', '')}".strip()


def field_text(section: ComposedSection, field: str) -> str | None:
    """Return the text that a field path names in a composed section, or None."""
    if field in ("title", "source_line"):
        return _written(section.props.get(field))
    if field.startswith("items["):
        match = ITEM.fullmatch(field)
        return _item_text(section, match) if match else None
    if field.startswith("paragraphs["):
        match = re.fullmatch(r"paragraphs\[(\d+)\]", field)
        paragraphs = section.props.get("paragraphs", [])
        if match and int(match.group(1)) < len(paragraphs):
            return _written(paragraphs[int(match.group(1))])
        return None
    if field.startswith("data"):
        if not re.fullmatch(r"data(?:\.[A-Za-z_]\w*|\[\d+\])*", field):
            return None
        parts = [(name, index) for name, index in PART.findall(field)][1:]
        return _written(_at(section.content.get("data"), parts))
    return None


def _item_index(field: str) -> int | None:
    match = re.match(r"items\[(\d+)\]", field)
    return int(match.group(1)) if match else None


def _citations(section: ComposedSection, field: str) -> list[Citation]:
    index = _item_index(field)
    lists = section.content.get("citations", [])
    if index is None or index >= len(lists):
        return []
    return [Citation(**citation) for citation in lists[index]]


def _innermost(elements: list[ElementMark], point: tuple[int, float, float]) -> ElementMark | None:
    containing = [mark for mark in elements if contains(mark, point)]
    return min(containing, key=lambda mark: mark.w * mark.h, default=None)


def number_marks(layout: LayoutFacts, composition: Composition) -> list[SourceMark]:
    """Return one mark per number of a placed word, with no supporting facts."""
    sections = {section.id: section for section in composition.sections}
    elements: dict[str, list[ElementMark]] = {}
    for mark in layout.marks:
        if isinstance(mark, ElementMark):
            elements.setdefault(mark.id, []).append(mark)
    kept: Counter[tuple[str, str, str]] = Counter()
    marks = []
    for word in layout.words:
        section = sections.get(word.section_id or "")
        if section is None:
            continue
        element = _innermost(elements.get(section.id, []), centre(word.box))
        if element is None or not element.field:
            continue
        text = field_text(section, element.field)
        if text is None:
            continue
        allowed = {token for token in support_tokens(text) if NUMBER.fullmatch(token)}
        occurrences = Counter(match.group().replace(",", "") for match in NUM.finditer(text))
        for match in NUM.finditer(word.text):
            token = match.group().replace(",", "")
            key = (section.id, element.field, token)
            if token not in allowed or kept[key] >= occurrences[token]:
                continue
            kept[key] += 1
            index = _item_index(element.field)
            cited = index is not None and bool(_citations(section, element.field))
            marks.append(
                SourceMark(
                    section=section.id,
                    field=element.field,
                    text=match.group(),
                    token=token,
                    cited=cited,
                    facts=[],
                    page=word.box.page,
                    x=word.box.x0,
                    y=word.box.y0,
                    w=word.box.x1 - word.box.x0,
                    h=word.box.y1 - word.box.y0,
                )
            )
    return marks


def source_marks(layout: LayoutFacts, composition: Composition, facts: Sequence[Fact]) -> list[SourceMark]:
    """Return the number marks, each with the ids of the facts that hold its number."""
    sections = {section.id: section for section in composition.sections}
    result = []
    for mark in number_marks(layout, composition):
        if mark.cited:
            citations = _citations(sections[mark.section], mark.field)
            candidates = [fact for citation in citations for fact in cited_facts(facts, citation)]
        else:
            candidates = list(facts)
        ids = {fact.id for fact in candidates if fact.id and mark.token in fact_number_tokens(fact)}
        result.append(mark.model_copy(update={"facts": sorted(ids)}))
    return result
