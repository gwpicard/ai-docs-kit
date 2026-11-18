from ai_docs_kit.checks.engine import CheckContext, run_checks
from ai_docs_kit.checks.text import RULES
from ai_docs_kit.model import Document, Item, Section


def test_intent_scoped_rule_fires_on_a_section_without_an_id():
    doc = Document(
        front={"title": "T"},
        format="slides",
        sections=[Section(intent="bullets", title="Why?", items=[Item(body="x")])],
    )
    rule = RULES[0]
    scoped = rule.model_copy(update={"scope": rule.scope.model_copy(update={"intents": ["bullets"]})})
    findings = run_checks([scoped], CheckContext(doc=doc))
    assert [f.rule_id for f in findings] == ["source.title-label"]
