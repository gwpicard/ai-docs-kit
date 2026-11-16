from ai_docs_kit.checks.engine import CheckContext
from ai_docs_kit.checks.text import RULES, BannedTerms
from ai_docs_kit.model import Document, Item, Section
from ai_docs_kit.theme import neutral_theme


def test_banned_term_ending_in_a_symbol_is_found(tmp_path):
    (tmp_path / "voice").mkdir()
    (tmp_path / "voice" / "terminology.yaml").write_text("banned: ['C++', 'win-win!']\n")
    theme = neutral_theme().model_copy(update={"root": tmp_path})
    doc = Document(
        front={"title": "T"},
        format="slides",
        sections=[Section(id="s1", intent="bullets", title="T", items=[Item(body="We chose C++ for speed.")])],
    )
    rule = next(r for r in RULES if r.id == "source.banned-terms")
    findings = BannedTerms().run(CheckContext(doc=doc, theme=theme), rule)
    assert [f.measured["terms"] for f in findings] == [["C++"]]
