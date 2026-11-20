from ai_docs_kit.checks.engine import CheckContext
from ai_docs_kit.checks.source import RULES, EmptySection
from ai_docs_kit.model import Document, Item, Section


def _findings(**fields):
    doc = Document(front={"title": "T"}, format="slides", sections=[Section(id="s1", intent="bullets", **fields)])
    rule = next(r for r in RULES if r.id == "source.empty-section")
    return EmptySection().run(CheckContext(doc=doc), rule)


def test_section_of_blank_text_is_empty():
    assert len(_findings(title="  ", items=[Item(body="")], paragraphs=[""])) == 1
