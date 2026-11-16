from ai_docs_kit.checks.engine import CheckContext
from ai_docs_kit.checks.figures import RULES, UncitedFigure
from ai_docs_kit.model import Document, Item, Section


def test_uncited_number_in_a_sub_item_is_reported():
    doc = Document(
        front={"title": "T"},
        format="slides",
        sections=[
            Section(id="s1", intent="bullets", title="T", items=[Item(body="Growth was strong.", sub=["Up 40%"])])
        ],
    )
    findings = UncitedFigure().run(CheckContext(doc=doc, final=True), RULES[0])
    assert len(findings) == 1
