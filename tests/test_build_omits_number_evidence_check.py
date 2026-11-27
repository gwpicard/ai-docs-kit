"""Builds must run the same source evidence check as the check command."""

import json

from ai_docs_kit.cli import main


def test_build_records_the_unsupported_number_found_by_check(tmp_path):
    """Record a number error in the built version as well as the check report."""
    source = tmp_path / "note.md"
    source.write_text(
        "---\ndoctype: pitch-deck\nformat: slides\ntitle: Readings\n---\n\n"
        "## Sources\n\n- [S1] readings.csv\n\n"
        '::: {#reading .section intent="bullets"}\n## Readings\n\n- The reading was 19. [S1]\n:::\n',
        encoding="utf-8",
    )
    facts = tmp_path / ".ai_docs_kit" / "write" / "note" / "facts.json"
    facts.parent.mkdir(parents=True)
    facts.write_text(json.dumps([{"text": "The reading was 12.", "source_key": "S1"}]), encoding="utf-8")
    checked = tmp_path / "checked"
    assert main(["check", str(source), "--out", str(checked)]) == 1
    reported = json.loads((checked / "note.findings.json").read_text(encoding="utf-8"))
    assert any(f["rule_id"] == "source.number-in-source" for f in reported)

    assert main(["build", str(source)]) == 0
    version = tmp_path / "note.versions" / "v1"
    built = json.loads((version / "findings.json").read_text(encoding="utf-8"))
    assert any(f["rule_id"] == "source.number-in-source" for f in built), (
        "build silently omitted the source.number-in-source error that check found on the same input"
    )
