"""Prepare one round of the document-building interview."""

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_docs_kit.agents.client import Claude
from ai_docs_kit.agents.gatherer import Fact
from ai_docs_kit.agents.prompts import system_blocks
from ai_docs_kit.doctypes import Doctype, RequiredField
from ai_docs_kit.intake.profile import Conflict, ReadBackItem
from ai_docs_kit.model.brief import Brief, BriefScope, Comparisons, Length, Metric, Topic
from ai_docs_kit.theme import Theme, neutral_theme

QuestionKind = Literal["scope", "coverage", "definitions", "conflicts", "form", "required_elements"]
ASKABLE_FIELDS: tuple[str, ...] = (
    "doctype",
    "scope",
    "topics",
    "metrics",
    "comparisons",
    "exclusions",
    "length",
    "required_elements",
)
KIND_FIELDS: dict[str, tuple[str, ...]] = {
    "scope": ("scope",),
    "coverage": ("topics", "exclusions"),
    "definitions": ("metrics", "comparisons"),
    "form": ("doctype", "length"),
    "required_elements": ("required_elements",),
    "conflicts": ASKABLE_FIELDS,
}
PREREQUISITES: dict[str, tuple[str, ...]] = {
    "length": ("doctype",),
    "required_elements": ("doctype",),
    "topics": ("scope",),
    "metrics": ("scope",),
    "comparisons": ("metrics",),
    "exclusions": ("topics",),
}
MAX_QUESTIONS = 4


class InterviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Option(InterviewModel):
    key: str
    text: str


class QuestionDraft(InterviewModel):
    kind: QuestionKind
    field: str
    title: str
    ask: str
    recommended: str
    options: list[Option] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class IntakeQuestion(QuestionDraft):
    id: str


class Answer(InterviewModel):
    question: str
    reply: str


class Correction(InterviewModel):
    field: str
    text: str


class AskedRound(InterviewModel):
    number: int
    questions: list[IntakeQuestion]
    answers: list[Answer] = Field(default_factory=list)
    corrections: list[Correction] = Field(default_factory=list)


class RequiredValue(InterviewModel):
    key: str
    value: str


class BriefUpdate(InterviewModel):
    doctype: str | None = None
    scope: BriefScope | None = None
    topics: list[Topic] | None = None
    metrics: list[Metric] | None = None
    comparisons: Comparisons | None = None
    exclusions: list[str] | None = None
    length: Length | None = None
    required_values: list[RequiredValue] | None = None


class InterviewerReply(InterviewModel):
    updates: BriefUpdate
    questions: list[QuestionDraft]


class InterviewTurn(InterviewModel):
    updates: BriefUpdate
    questions: list[IntakeQuestion]
    dropped: list[QuestionDraft]


def frontier(brief: Brief, *, missing_values: Sequence[str] = ()) -> list[str]:
    return [
        field
        for field in ASKABLE_FIELDS
        if (brief.status(field) is None or (field == "required_elements" and missing_values))
        and all(brief.status(prerequisite) is not None for prerequisite in PREREQUISITES.get(field, ()))
    ]


def _prompt(
    brief: Brief,
    doctype: Doctype | None,
    facts: Sequence[Fact],
    read_back: Sequence[ReadBackItem],
    conflicts: Sequence[Conflict],
    missing: Sequence[RequiredField],
    history: Sequence[AskedRound],
    final: bool,
    fields: list[str],
) -> str:
    lines = [f"Request: {brief.request}", f"Format: {brief.format} (length in {brief.length_unit()})"]
    if doctype is None:
        lines.append("Doctype: none")
    else:
        lines.extend(
            [
                f"Doctype: {doctype.name}",
                f"Audience: {doctype.audience}",
                f"Parts: {', '.join(part.section for part in doctype.outline)}",
                f"Required fields: {', '.join(f'{item.key}: {item.ask}' for item in doctype.required_fields)}",
            ]
        )
    lines.append("Read-back:")
    lines.extend(f"{item.field} ({item.status}): {item.text}" for item in read_back)
    lines.append("Conflicts:")
    lines.extend(
        f"{item.label}, {item.header}: {' or '.join(item.values)} [{', '.join(item.sources)}]" for item in conflicts
    )
    lines.append(f"Frontier: {', '.join(fields)}")
    lines.extend(f"Missing: {item.key}: {item.ask}" for item in missing)
    lines.append("Facts:")
    lines.extend(f"{item.id or ''} [{item.source_key} {item.locator or ''}] {item.text}" for item in facts)
    for round_ in history:
        lines.append(f"Round {round_.number}:")
        answers = {answer.question: answer.reply for answer in round_.answers}
        for q in round_.questions:
            line = f"{q.id} {q.title}: {q.ask} | recommended: {q.recommended} | answer: {answers.get(q.id, '')}"
            if q.options:
                # An answer such as "b" names an option; give its text so the reply can be read.
                line += " | options: " + "; ".join(f"{option.key}) {option.text}" for option in q.options)
            lines.append(line)
        lines.extend(f"Correction {item.field}: {item.text}" for item in round_.corrections)
    if final:
        lines.append("Final round: no questions.")
    return "\n".join(lines)


def _allowed(question: QuestionDraft, fields: list[str], conflicts: Sequence[Conflict], final: bool) -> bool:
    eligible = {item.field for item in conflicts} if question.kind == "conflicts" else set(fields)
    return (
        not final
        and question.field in ASKABLE_FIELDS
        and question.field in KIND_FIELDS[question.kind]
        and question.field in eligible
        and bool(question.recommended.strip())
    )


async def next_round(
    claude: Claude,
    *,
    brief: Brief,
    doctype: Doctype | None,
    facts: Sequence[Fact],
    read_back: Sequence[ReadBackItem],
    conflicts: Sequence[Conflict],
    missing: Sequence[RequiredField],
    history: Sequence[AskedRound],
    final: bool = False,
    theme: Theme | None = None,
) -> InterviewTurn:
    fields = frontier(brief, missing_values=[item.key for item in missing])
    prompt = _prompt(brief, doctype, facts, read_back, conflicts, missing, history, final, fields)
    reply = await claude.call(
        "interviewer",
        InterviewerReply,
        system=system_blocks("interviewer", theme or neutral_theme()),
        content=[{"type": "text", "text": prompt}],
        effort="medium",
    )
    questions: list[IntakeQuestion] = []
    dropped: list[QuestionDraft] = []
    for question in reply.questions:
        if len(questions) < MAX_QUESTIONS and _allowed(question, fields, conflicts, final):
            questions.append(IntakeQuestion(**question.model_dump(), id=f"Q{len(questions) + 1}"))
        else:
            dropped.append(question)
    return InterviewTurn(updates=reply.updates, questions=questions, dropped=dropped)
