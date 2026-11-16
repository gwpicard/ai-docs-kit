from ai_docs_kit.checks.engine import CheckContext
from ai_docs_kit.checks.text import RULES, TerminologyDrift
from ai_docs_kit.model import Document, Item, Section
from ai_docs_kit.theme import neutral_theme


def test_avoided_term_ending_in_a_symbol_is_found(tmp_path):
    (tmp_path / "voice").mkdir()
    (tmp_path / "voice" / "terminology.yaml").write_text("terminology:\n  - preferred: Rust\n    avoid: ['C++']\n")
    theme = neutral_theme().model_copy(update={"root": tmp_path})
    doc = Document(
        front={"title": "T"},
        format="slides",
        sections=[Section(id="s1", intent="bullets", title="T", items=[Item(body="We chose C++ for speed.")])],
    )
    rule = next(r for r in RULES if r.id == "source.terminology-drift")
    findings = TerminologyDrift().run(CheckContext(doc=doc, theme=theme), rule)
    assert [f.measured["avoid"] for f in findings] == [["C++"]]
