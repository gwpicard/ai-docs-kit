from ai_docs_kit.checks import source, text  # noqa: F401  (register checks)
from ai_docs_kit.checks.engine import CheckContext, run_checks
from ai_docs_kit.facts.layout import LayoutFacts
from ai_docs_kit.model import Document, Item, Provenance, Remedy, Rule, Section


def _rule(rule_id, tier, check):
    return Rule(
        id=rule_id,
        title="t",
        origin="manual",
        strength="hard",
        status="active",
        severity="error",
        tier=tier,
        check=check,
        remedy=Remedy.model_validate({"class": "redraft", "hint": "h"}),
        provenance=Provenance(source={"doc": "DESIGN.md", "section": "1"}),
    )


def test_error_in_one_idless_section_does_not_hide_another_sections_later_finding():
    # Section one is empty (a source error); section two has a title ending in "?" which a
    # later-tier all-of rule flags. Neither section has an id, so both findings carry
    # section_id None, and the first error must not block the second section's finding.
    doc = Document(
        front={"title": "T"},
        format="slides",
        sections=[
            Section(intent="bullets"),
            Section(intent="bullets", title="Why?", items=[Item(body="x")]),
        ],
    )
    empty = _rule("source.empty-section", "source", {"kind": "empty-section"})
    later = _rule(
        "geo.question-title",
        "geometry",
        {
            "kind": "all-of",
            "checks": [{"kind": "text-pattern", "field": "title", "regex": r"\?$", "must_not_match": True}],
        },
    )
    facts = LayoutFacts(pdf_sha256="x", pages=[], words=[], shapes=[], marks=[])
    findings = run_checks([empty, later], CheckContext(doc=doc, facts=facts))
    assert {f.rule_id for f in findings} == {"source.empty-section", "geo.question-title"}
