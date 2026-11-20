"""Builds retain number evidence findings alongside supported sections in either order."""

import json

import pytest

from ai_docs_kit.cli import main


@pytest.mark.parametrize("reverse", [False, True], ids=["unsupported-first", "unsupported-last"])
def test_build_preserves_number_evidence_by_cited_source_in_either_order(tmp_path, reverse):
    """A number supported by another source still produces the same error as check."""
    source = tmp_path / "readings.md"
    sections = [
        '::: {#unsupported .section intent="bullets"}\n## First reading\n\n- The reading was 12. [S1]\n:::\n',
        '::: {#supported .section intent="bullets"}\n## Other reading\n\n- The reading was 19. [S2]\n:::\n',
    ]
    facts = [
        {"text": "The reading was 12.", "source_key": "S1"},
        {"text": "The reading was 19.", "source_key": "S2"},
    ]
    if reverse:
        sections.reverse()
        facts.reverse()
    text = (
        "---\ndoctype: pitch-deck\nformat: slides\ntitle: Readings\n---\n\n"
        "## Sources\n\n- [S1] first.csv\n- [S2] other.csv\n\n" + "\n".join(sections)
    )
    source.write_text(text, encoding="utf-8")
    stored = tmp_path / ".ai_docs_kit" / "write" / "readings" / "facts.json"
    stored.parent.mkdir(parents=True)
    stored.write_text(json.dumps(facts), encoding="utf-8")

    checked = tmp_path / "checked"
    assert main(["check", str(source), "--out", str(checked)]) == 0
    clean_report = json.loads((checked / "readings.findings.json").read_text(encoding="utf-8"))
    assert not any(f["rule_id"] == "source.number-in-source" for f in clean_report)
    assert main(["build", str(source)]) == 0
    versions = tmp_path / "readings.versions"
    clean_build = json.loads((versions / "v1" / "findings.json").read_text(encoding="utf-8"))
    assert not any(f["rule_id"] == "source.number-in-source" for f in clean_build)

    source.write_text(text.replace("12. [S1]", "19. [S1]"), encoding="utf-8")
    assert main(["check", str(source), "--out", str(checked)]) == 1
    reported = json.loads((checked / "readings.findings.json").read_text(encoding="utf-8"))
    expected = [("unsupported", "19", ["S1"], "error", "source")]
    assert [
        (f["section_id"], f["measured"]["number"], f["measured"]["citations"], f["severity"], f["tier"])
        for f in reported
        if f["rule_id"] == "source.number-in-source"
    ] == expected

    assert main(["build", str(source)]) == 0
    built = json.loads((versions / "v2" / "findings.json").read_text(encoding="utf-8"))
    assert [
        (f["section_id"], f["measured"]["number"], f["measured"]["citations"], f["severity"], f["tier"])
        for f in built
        if f["rule_id"] == "source.number-in-source"
    ] == expected, "build must retain check's number error without flagging the supported section"
