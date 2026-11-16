from ai_docs_kit.checks.engine import CheckContext, run_checks
from ai_docs_kit.checks.fit import RULES
from ai_docs_kit.facts.layout import LayoutFacts
from ai_docs_kit.model import Document, Section
from ai_docs_kit.render.marks import FitMark


def test_two_overflowing_frames_of_one_role_are_both_reported():
    doc = Document(front={"title": "T"}, format="slides", sections=[Section(id="s1", intent="bullets", title="T")])
    marks = [
        FitMark(kind="fit", role="item", id="s1", need=300, have=100, ok=False),
        FitMark(kind="fit", role="item", id="s1", need=500, have=100, ok=False),
    ]
    facts = LayoutFacts(pdf_sha256="x", pages=[], words=[], shapes=[], marks=marks)
    findings = run_checks(RULES, CheckContext(doc=doc, facts=facts))
    assert sorted(f.measured["over"] for f in findings) == [200.0, 400.0]
