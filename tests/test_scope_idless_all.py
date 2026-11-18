import pytest

from ai_docs_kit.checks import source  # noqa: F401  (register checks)
from ai_docs_kit.checks.engine import CheckContext, run_checks
from ai_docs_kit.checks.text import RULES
from ai_docs_kit.model import Document, Item, Section
from ai_docs_kit.model.rules import Scope
from ai_docs_kit.render.compose import compose


def _doc(with_ids: bool) -> Document:
    def section(n: int, intent: str, title: str) -> Section:
        return Section(id=f"aaaa{n}" if with_ids else None, intent=intent, title=title, items=[Item(body="x")])

    return Document(
        front={"title": "T"},
        format="slides",
        sections=[section(1, "bullets", "Why?"), section(2, "bullets", "What?"), section(3, "statement", "Fine")],
    )


def _scope(name: str) -> Scope:
    composed = compose(_doc(True)).sections
    values = {
        "components": [composed[0].component],
        "intents": ["bullets"],
        "roles": ["title"],
        "format": "slides",
    }
    return Scope.model_validate({name: values[name]})


def test_every_scope_key_is_covered():
    assert set(Scope.model_fields) == {"format", "roles", "components", "intents"}


@pytest.mark.parametrize("name", sorted(Scope.model_fields))
def test_scoped_rule_gives_the_same_findings_with_and_without_ids(name):
    rule = RULES[0].model_copy(update={"scope": _scope(name)})
    with_ids = _doc(True)
    # The composition needs ids, so both runs share it; it lines up with the sections by position.
    composition = compose(with_ids)

    def run(doc):
        return run_checks([rule], CheckContext(doc=doc, composition=composition))

    expected = run(with_ids)
    actual = run(_doc(False))
    assert [f.rule_id for f in expected] == ["source.title-label"] * 2
    assert [(f.rule_id, f.message, f.severity) for f in actual] == [
        (f.rule_id, f.message, f.severity) for f in expected
    ]
