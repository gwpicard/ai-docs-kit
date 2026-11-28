"""Source quotations span a bullet's bold head and body, but not separate items."""

import json

import pytest

from ai_docs_kit.cli import main


@pytest.mark.parametrize("opening, closing", [('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’")])
@pytest.mark.parametrize("command, fmt", [("check", "doc"), ("build", "slides")])
def test_source_quotation_spans_only_its_own_item_head_and_body(tmp_path, capsys, opening, closing, command, fmt):
    bodies = {
        "plain": f"- {opening}unlock practical progress{closing} [S1]",
        "verified": f"- **{opening}unlock** practical progress{closing} [S1]",
        "unsupported": f"- **{opening}unlock** a secret switch{closing} [S1]",
        "unquoted": "- **unlock** practical progress [S1]",
        "mixed-head": f"- **unlock {opening}unlock** practical progress{closing} [S1]",
        "mixed-body": f"- **{opening}unlock** practical progress{closing}; unlock [S1]",
        "separate-items": f"- {opening}unlock [S1]\n- practical progress{closing} [S1]",
        "nested-closure": f"- **{opening}unlock** [S1]\n  - practical progress{closing}",
        "nested-unquoted": f"- **{opening}unlock** practical progress{closing} [S1]\n  - unlock",
    }
    working = tmp_path / "readout.md"
    working.write_text(
        f"---\nformat: {fmt}\n---\n\n## Sources\n\n- [S1] unlock practical progress\n\n"
        + "\n".join(
            f'::: {{#{section_id} .section intent="bullets"}}\n## Findings\n\n{body}\n:::\n'
            for section_id, body in bodies.items()
        ),
        encoding="utf-8",
    )

    assert main([command, str(working)]) == (1 if command == "check" else 0)
    assert capsys.readouterr().err == ""
    report = (
        tmp_path / "build" / "readout.findings.json"
        if command == "check"
        else tmp_path / "readout.versions" / "v1" / "findings.json"
    )
    banned = [finding for finding in json.loads(report.read_bytes()) if finding["rule_id"] == "source.banned-terms"]
    assert {finding["section_id"] for finding in banned} == set(bodies) - {"plain", "verified"}
    assert all(finding["measured"] == {"field": "items", "terms": ["unlock"]} for finding in banned)
