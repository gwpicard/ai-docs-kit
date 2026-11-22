from ai_docs_kit.checks.engine import CheckContext
from ai_docs_kit.checks.text import RULES, BannedTerms
from ai_docs_kit.model import Document, Item, Section
from ai_docs_kit.theme import neutral_theme


def _doc(**fields):
    return Document(
        front={"title": "T"},
        format="slides",
        sections=[Section(id="s1", intent="bullets", title="T", items=[Item(body="Plain words.")], **fields)],
    )


def _run(tmp_path, doc):
    (tmp_path / "voice").mkdir(exist_ok=True)
    (tmp_path / "voice" / "terminology.yaml").write_text("banned: ['synergy']\n")
    theme = neutral_theme().model_copy(update={"root": tmp_path})
    rule = next(r for r in RULES if r.id == "source.banned-terms")
    return BannedTerms().run(CheckContext(doc=doc, theme=theme), rule)


def test_a_banned_term_in_spoken_text_is_found(tmp_path):
    findings = _run(tmp_path, _doc(spoken="We will talk about synergy."))
    assert [f.measured["field"] for f in findings] == ["spoken"]


def test_a_banned_term_in_a_note_or_source_line_is_not_a_finding(tmp_path):
    assert _run(tmp_path, _doc(note="synergy", source_line="Synergy report")) == []
