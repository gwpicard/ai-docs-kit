from ai_docs_kit.checks.engine import CheckContext, run_checks
from ai_docs_kit.checks.text import RULES
from ai_docs_kit.model import Document, Section


def test_two_sections_without_ids_each_get_their_finding():
    doc = Document(
        front={"title": "T"},
        format="slides",
        sections=[
            Section(intent="bullets", title="Is this ready?"),
            Section(intent="bullets", title="Is that ready?"),
        ],
    )
    rule = next(r for r in RULES if r.id == "source.title-label")
    findings = run_checks([rule], CheckContext(doc=doc))
    assert len(findings) == 2
