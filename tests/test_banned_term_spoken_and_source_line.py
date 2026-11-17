from ai_docs_kit.checks.engine import CheckContext
from ai_docs_kit.checks.text import RULES, BannedTerms
from ai_docs_kit.model import Document, Item, Section
from ai_docs_kit.theme import neutral_theme


def test_a_banned_term_in_spoken_text_or_a_source_line_is_found(tmp_path):
    (tmp_path / "voice").mkdir()
    (tmp_path / "voice" / "terminology.yaml").write_text("banned: ['synergy']\n")
    theme = neutral_theme().model_copy(update={"root": tmp_path})
    doc = Document(
        front={"title": "T"},
        format="slides",
        sections=[
            Section(
                id="s1",
                intent="bullets",
                title="T",
                items=[Item(body="Plain words.")],
                spoken="We will talk about synergy.",
                source_line="Synergy report",
            )
        ],
    )
    rule = next(r for r in RULES if r.id == "source.banned-terms")
    assert BannedTerms().run(CheckContext(doc=doc, theme=theme), rule) != []
