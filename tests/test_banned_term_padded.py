from ai_docs_kit.checks.engine import CheckContext
from ai_docs_kit.checks.text import RULES, BannedTerms, TerminologyDrift
from ai_docs_kit.model import Document, Item, Section
from ai_docs_kit.theme import neutral_theme


def _run(tmp_path, yaml, body, check, rule_id):
    (tmp_path / "voice").mkdir()
    (tmp_path / "voice" / "terminology.yaml").write_text(yaml)
    theme = neutral_theme().model_copy(update={"root": tmp_path})
    doc = Document(
        front={"title": "T"},
        format="slides",
        sections=[Section(id="s1", intent="bullets", title="T", items=[Item(body=body)])],
    )
    rule = next(r for r in RULES if r.id == rule_id)
    return check.run(CheckContext(doc=doc, theme=theme), rule)


def test_banned_term_with_padding_is_still_found(tmp_path):
    findings = _run(tmp_path, "banned: [' synergy ']\n", "We want synergy.", BannedTerms(), "source.banned-terms")
    assert len(findings) == 1


def test_avoided_term_with_padding_is_still_found(tmp_path):
    yaml = "terminology: [{preferred: use, avoid: [' utilise ']}]\n"
    findings = _run(tmp_path, yaml, "We utilise.", TerminologyDrift(), "source.terminology-drift")
    assert len(findings) == 1
