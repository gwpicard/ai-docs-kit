import pytest

from ai_docs_kit.agents.gatherer import Fact
from ai_docs_kit.checks.catalogue import all_rules
from ai_docs_kit.checks.engine import CheckContext, run_checks
from ai_docs_kit.model import Citation, Document, Item, Section
from ai_docs_kit.theme import neutral_theme


def _sections(*make: Section) -> list[Section]:
    return list(make)


def _ctx(tmp_path, doc: Document, **extra) -> CheckContext:
    voice = tmp_path / "voice"
    voice.mkdir()
    (voice / "terminology.yaml").write_text(
        "banned: ['synergy']\nterminology:\n  - {preferred: customer, avoid: [client]}\n"
    )
    theme = neutral_theme().model_copy(update={"root": tmp_path})
    return CheckContext(doc=doc, theme=theme, **extra)


def _doc(fmt, *sections: Section) -> Document:
    return Document(front={"title": "T"}, format=fmt, sections=list(sections))


def _bullets(title: str, **fields) -> Section:
    return Section(intent="bullets", title=title, **fields)


def _cited(body: str, key: str = "S1") -> list[Item]:
    return [Item(body=body, citations=[Citation(key=key)])]


# Per-section families: rule id -> (document, extra CheckContext arguments).
# Out of scope, because the finding is per document or needs a section id to
# locate marks: source.outline-conforms and every geometry, pixel and
# font rule.
CASES = {
    "source.citations-resolve": (
        lambda: _doc("slides", _bullets("A", items=_cited("One.")), _bullets("B", items=_cited("Two."))),
        {},
    ),
    "source.empty-section": (lambda: _doc("slides", Section(intent="bullets"), Section(intent="bullets")), {}),
    "source.intent-known": (
        lambda: _doc("slides", Section(intent="body", title="A"), Section(intent="body", title="B")),
        {},
    ),
    "source.title-label": (lambda: _doc("slides", _bullets("Why?"), _bullets("What?")), {}),
    "source.banned-terms": (
        lambda: _doc(
            "slides",
            _bullets("A", items=[Item(body="Our synergy grows.")]),
            _bullets("B", items=[Item(body="More synergy here.")]),
        ),
        {},
    ),
    "source.terminology-drift": (
        lambda: _doc(
            "slides",
            _bullets("A", items=[Item(body="Ask the client.")]),
            _bullets("B", items=[Item(body="Call the client.")]),
        ),
        {},
    ),
    "source.capacity": (
        lambda: _doc(
            "slides",
            _bullets("A", items=[Item(body=f"Point {i}.") for i in range(9)]),
            _bullets("B", items=[Item(body=f"Point {i}.") for i in range(9)]),
        ),
        {},
    ),
    "source.gap-present": (
        lambda: _doc(
            "slides",
            _bullets("A", items=[Item(body="Revenue is [GAP: revenue].")]),
            _bullets("B", items=[Item(body="Cost is [GAP: cost].")]),
        ),
        {},
    ),
    "source.uncited-figure": (
        lambda: _doc(
            "slides",
            _bullets("A", items=[Item(body="Sales rose 12 units.")]),
            _bullets("B", items=[Item(body="Costs fell 7 units.")]),
        ),
        {"final": True},
    ),
    "source.image-resolves": (
        lambda: _doc(
            "slides",
            Section(intent="bullets", title="A", image="missing-a.png"),
            Section(intent="bullets", title="B", image="missing-b.png"),
        ),
        {"assets": []},
    ),
    "source.number-in-source": (
        lambda: _doc(
            "slides",
            _bullets("A", items=_cited("Sales rose 99.")),
            _bullets("B", items=_cited("Costs rose 99.")),
        ),
        {"source_facts": [Fact(text="Sales rose 12.", source_key="S1", kind="number")]},
    ),
}


@pytest.mark.parametrize("rule_id", sorted(CASES))
def test_two_sections_without_ids_give_two_distinct_findings(tmp_path, rule_id):
    make_doc, extra = CASES[rule_id]
    if "assets" in extra:
        extra = {**extra, "assets": [tmp_path]}
    rule = next(r for r in all_rules() if r.id == rule_id)
    doc = make_doc()
    assert all(section.id is None for section in doc.sections)
    findings = run_checks([rule], _ctx(tmp_path, doc, **extra))
    assert len(findings) == 2
    assert len({f.id for f in findings}) == 2
    assert len({f.fingerprint for f in findings}) == 2
