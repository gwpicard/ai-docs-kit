"""Source quotations retain punctuation where a bold bullet head meets its body."""

import json

import pytest

from ai_docs_kit.cli import main


@pytest.mark.parametrize("punctuation", [":", ",", ";", "."])
@pytest.mark.parametrize("opening, closing", [('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’")])
def test_check_preserves_source_quote_punctuation_across_a_bold_head(tmp_path, capsys, punctuation, opening, closing):
    wording = f"unlock{punctuation} practical progress"
    bodies = {
        "plain": f"{opening}{wording}{closing}",
        "supported": f"**{opening}unlock**{punctuation} practical progress{closing}",
        "unsupported": f"**{opening}unlock**{punctuation} a hidden switch{closing}",
        "unquoted": f"**unlock**{punctuation} practical progress",
        "mixed": f"**{opening}unlock**{punctuation} practical progress{closing}; unlock",
    }
    working = tmp_path / "readout.md"
    working.write_text(
        f"---\nformat: doc\n---\n\n## Sources\n\n- [S1] {wording}\n\n"
        + "\n".join(
            f'::: {{#{section_id} .section intent="bullets"}}\n## Findings\n\n- {body} [S1]\n:::\n'
            for section_id, body in bodies.items()
        ),
        encoding="utf-8",
    )

    assert main(["check", str(working), "--outline"]) == 1
    assert capsys.readouterr().err == ""
    report = tmp_path / "build" / "readout.findings.json"
    banned = [finding for finding in json.loads(report.read_bytes()) if finding["rule_id"] == "source.banned-terms"]
    assert {finding["section_id"] for finding in banned} == {"unsupported", "unquoted", "mixed"}
    assert all(finding["measured"] == {"field": "items", "terms": ["unlock"]} for finding in banned)
