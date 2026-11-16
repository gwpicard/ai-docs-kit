# Intent: interview the person about decisions needed to build the document.
import asyncio
import importlib
import importlib.util
import json

import pytest

from ai_docs_kit import doctypes
from ai_docs_kit.agents import client, gatherer, prompts
from ai_docs_kit.config import ProjectConfig
from ai_docs_kit.model.brief import Brief, FieldProvenance
from ai_docs_kit.testing import fakes
from ai_docs_kit.theme import neutral_theme
from ai_docs_kit.write import role_models


def optional(name):
    try:
        return importlib.import_module(name)
    except ImportError as error:
        if error.name != name and not name.startswith(f"{error.name}."):
            raise
        try:
            spec = importlib.util.find_spec(name)
        except ModuleNotFoundError as missing:
            if not name.startswith(f"{missing.name}."):
                raise
            spec = None
        if spec is not None:
            raise
        return None


interviewer = optional("ai_docs_kit.agents.interviewer")
profile = optional("ai_docs_kit.intake.profile")


def need():
    assert interviewer is not None, "ai_docs_kit.agents.interviewer must exist"
    for name in ("frontier", "next_round", "IntakeQuestion", "Answer", "Correction", "AskedRound"):
        assert hasattr(interviewer, name), f"interviewer.{name} must exist"


class Ledger:
    def add(self, role, model, usage):
        pass


def question(kind, field, title):
    return {"kind": kind, "field": field, "title": title, "ask": f"Use {title}?",
            "recommended": f"Use {title}", "options": [], "evidence": []}


def run_turn(brief, questions, *, updates=None, conflicts=(), missing=(), history=(), final=False, facts=()):
    response = {"updates": updates or {}, "questions": questions}
    transport = fakes.FakeTransport({"claude-opus-5-5": [fakes.fake_response(json.dumps(response))]})
    claude = client.Claude(transport, Ledger(), {"interviewer": "claude-opus-5-5"})
    turn = asyncio.run(interviewer.next_round(
        claude, brief=brief, doctype=None, facts=facts, read_back=[], conflicts=conflicts,
        missing=missing, history=history, final=final,
    ))
    assert len(transport.requests) == 1
    return turn, transport.requests[0]


def text(request):
    return "\n".join(block["text"] for block in request["messages"][0]["content"] if block["type"] == "text")


def settled(*fields):
    return {field: FieldProvenance(status="defaulted") for field in fields}


def author():
    assert hasattr(doctypes, "RequiredField"), "doctypes.RequiredField must exist"
    return doctypes.RequiredField(key="author", label="Author", ask="Who is named as the author?")


def conflict():
    assert profile is not None and hasattr(profile, "Conflict"), "intake.profile.Conflict must exist"
    return profile.Conflict(field="metrics", label="Partner channel", header="Revenue",
                            values=["£1,234,500", "£1,300,000"], evidence=["Fab12", "Fcd34"],
                            sources=["S1 sales!B2", "S2 targets!B2"])


def test_D1_frontier_prerequisites_and_missing_values():
    need()
    assert interviewer.frontier(Brief(format="slides")) == ["doctype", "scope"]
    brief = Brief(format="slides", provenance=settled("doctype", "scope"))
    assert interviewer.frontier(brief) == ["topics", "metrics", "length", "required_elements"]
    brief.provenance["metrics"] = FieldProvenance(status="confirmed")
    assert interviewer.frontier(brief) == ["topics", "comparisons", "length", "required_elements"]
    brief.provenance["required_elements"] = FieldProvenance(status="defaulted")
    assert interviewer.frontier(brief) == ["topics", "comparisons", "length"]
    assert interviewer.frontier(brief, missing_values=["author"]) == ["topics", "comparisons", "length", "required_elements"]
    for status in ("confirmed", "skipped", "inferred"):
        brief.provenance["scope"] = FieldProvenance(status=status, evidence=["F1"] if status == "inferred" else [])
        assert interviewer.frontier(brief) == ["topics", "comparisons", "length"]


def test_D2_request_and_role_configuration():
    need()
    brief = Brief(format="slides", request="Q3 sales for the board", provenance=settled("doctype"))
    fact = gatherer.Fact(id="Fab12", source_key="S1", locator="sales!B2", text="Partner channel, Revenue: £1,234,500")
    _, request = run_turn(brief, [], facts=[fact], conflicts=[conflict()], missing=[author()])
    assert request["model"] == "claude-opus-5-5"
    assert request["system"] == prompts.system_blocks("interviewer", neutral_theme())
    prompt = text(request)
    assert "Request: Q3 sales for the board" in prompt
    assert "Frontier: scope, length, required_elements" in prompt
    assert "Fab12 [S1 sales!B2] Partner channel, Revenue: £1,234,500" in prompt
    assert "Partner channel, Revenue: £1,234,500 or £1,300,000 [S1 sales!B2, S2 targets!B2]" in prompt
    assert "Missing: author: Who is named as the author?" in prompt
    assert prompts.ROLES == ("gatherer", "planner", "writer.draft", "writer.repair")
    with pytest.raises(ValueError):
        prompts.system_blocks("critic", neutral_theme())
    assert role_models(ProjectConfig())["interviewer"] == "claude-opus-5-5"


def test_D3_filter_frontier_kind_strategy_and_conflicts():
    need()
    brief = Brief(format="slides", provenance=settled("doctype"))
    questions = [question("scope", "scope", "period"), question("form", "length", "length"),
                 question("required_elements", "required_elements", "author"),
                 question("definitions", "key_message", "message"), question("scope", "length", "wrong kind"),
                 question("form", "tone", "tone"), question("definitions", "metrics", "measure")]
    turn, _ = run_turn(brief, questions, missing=[author()])
    assert [(q.id, q.title, q.recommended) for q in turn.questions] == [
        ("Q1", "period", "Use period"), ("Q2", "length", "Use length"), ("Q3", "author", "Use author")]
    assert [q.title for q in turn.dropped] == ["message", "wrong kind", "tone", "measure"]
    disputed = question("conflicts", "metrics", "source")
    accepted, _ = run_turn(brief, [disputed], conflicts=[conflict()])
    rejected, _ = run_turn(brief, [disputed])
    assert [(q.id, q.title) for q in accepted.questions] == [("Q1", "source")]
    assert rejected.questions == []
    assert [q.title for q in rejected.dropped] == ["source"]
    blank = question("scope", "scope", "blank")
    blank["recommended"] = "  "
    rejected, _ = run_turn(brief, [blank])
    assert rejected.questions == [] and [q.title for q in rejected.dropped] == ["blank"]


def test_D4_limit_and_final_preserves_updates():
    need()
    brief = Brief(format="slides")
    questions = [question("scope", "scope", f"period {n}") for n in range(1, 6)]
    updates = {"scope": {"period": "Q3 FY26"}, "required_values": [{"key": "author", "value": "Jane Doe"}]}
    turn, _ = run_turn(brief, questions, updates=updates)
    assert [(q.id, q.title) for q in turn.questions] == [("Q1", "period 1"), ("Q2", "period 2"),
                                                        ("Q3", "period 3"), ("Q4", "period 4")]
    assert [q.title for q in turn.dropped] == ["period 5"]
    final, request = run_turn(brief, questions, updates=updates, final=True)
    assert final.questions == []
    assert [q.title for q in final.dropped] == [f"period {n}" for n in range(1, 6)]
    assert final.updates.scope.period == "Q3 FY26"
    assert [(v.key, v.value) for v in final.updates.required_values] == [("author", "Jane Doe")]
    assert "Final round: no questions." in text(request)


def test_D5_history_corrections_and_doc_format():
    need()
    earlier = [interviewer.IntakeQuestion(id=f"Q{n}", **question("scope", "scope", title))
               for n, title in enumerate(("period", "entities", "sources"), 1)]
    history = [interviewer.AskedRound(number=1, questions=earlier,
               answers=[interviewer.Answer(question=f"Q{n}", reply=reply)
                        for n, reply in enumerate(("yes", "skip", "b"), 1)],
               corrections=[interviewer.Correction(field="scope", text="The period is Q3 FY26")])]
    brief = Brief(format="doc", provenance=settled("doctype"))
    turn, request = run_turn(brief, [question("form", "length", "length"), question("form", "tone", "tone")], history=history)
    prompt = text(request)
    assert "Format: doc (length in pages)" in prompt
    assert "Round 1:" in prompt
    for n, title, reply in ((1, "period", "yes"), (2, "entities", "skip"), (3, "sources", "b")):
        assert f"Q{n} {title}: Use {title}? | recommended: Use {title} | answer: {reply}" in prompt
    assert "Correction scope: The period is Q3 FY26" in prompt
    assert [(q.id, q.title) for q in turn.questions] == [("Q1", "length")]
    assert [q.title for q in turn.dropped] == ["tone"]
