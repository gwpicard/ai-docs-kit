"""Citation resolution also checks references in prose sections."""

import json

import pytest

from ai_docs_kit.cli import main


@pytest.mark.parametrize(("fmt", "intent"), [("doc", "body"), ("slides", "statement")])
def test_unlisted_prose_citation_is_reported_after_a_valid_control(tmp_path, fmt, intent):
    source = tmp_path / "note.md"
    text = (
        f"---\ndoctype: report\nformat: {fmt}\ntitle: Note\n---\n\n"
        "## Sources\n\n- [S1] notes.txt, workshop notes\n\n"
        f'::: {{#timing .section intent="{intent}"}}\n## Timing\n\n'
        "The plan names a date. [S1 p.4]\n:::\n"
    )
    source.write_text(text, encoding="utf-8")
    control = tmp_path / "control"
    assert main(["check", str(source), "--out", str(control)]) == 0
    assert json.loads((control / "note.findings.json").read_text(encoding="utf-8")) == []
    source.write_text(text.replace("[S1 p.4]", "[S99 p.4]"), encoding="utf-8")
    out = tmp_path / "unlisted"

    code = main(["check", str(source), "--out", str(out)])
    findings = json.loads((out / "note.findings.json").read_text(encoding="utf-8"))

    assert code == 1, f"The unlisted prose citation passed: {findings}"
    hits = [finding for finding in findings if finding["rule_id"] == "source.citations-resolve"]
    assert [(hit["section_id"], hit["measured"]["key"]) for hit in hits] == [("timing", "S99")]
