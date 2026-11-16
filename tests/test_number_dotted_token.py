from ai_docs_kit.agents.gatherer import Fact
from ai_docs_kit.checks.engine import CheckContext
from ai_docs_kit.checks.numbers import RULES, NumberInSource
from ai_docs_kit.model import Citation, Document, Item, Section


def test_dotted_reference_number_does_not_crash_the_check():
    doc = Document(
        front={"title": "T"},
        format="slides",
        sections=[
            Section(
                id="s1",
                intent="bullets",
                title="T",
                items=[Item(body="See clause 1.2.3 for the 12 units.", citations=[Citation(key="S1")])],
            )
        ],
    )
    facts = [Fact(text="12 units", source_key="S1")]
    ctx = CheckContext(doc=doc, source_facts=facts)
    findings = NumberInSource().run(ctx, RULES[0])
    assert [f.measured["number"] for f in findings] == ["1.2.3"]
