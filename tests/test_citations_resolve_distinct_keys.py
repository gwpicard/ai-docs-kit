from ai_docs_kit.checks.engine import CheckContext, run_checks
from ai_docs_kit.checks.source import RULES
from ai_docs_kit.model import Citation, Document, Item, Section


def test_each_unlisted_citation_key_is_reported():
    doc = Document(
        front={"title": "T"},
        format="slides",
        sections=[
            Section(
                id="s1",
                intent="bullets",
                title="T",
                items=[
                    Item(body="One.", citations=[Citation(key="S1")]),
                    Item(body="Two.", citations=[Citation(key="S2")]),
                ],
            )
        ],
    )
    rule = next(r for r in RULES if r.id == "source.citations-resolve")
    findings = run_checks([rule], CheckContext(doc=doc))
    assert sorted(f.measured["key"] for f in findings) == ["S1", "S2"]
