"""Scratch previews and saved builds locate the same source findings."""

import json

import pytest

from ai_docs_kit import api
from ai_docs_kit.cli import main


@pytest.mark.parametrize("fmt, maximum, page", [("slides", 140, 3), ("doc", 240, 1)])
def test_preview_keeps_capacity_and_parser_locations_in_step_with_build(tmp_path, capsys, fmt, maximum, page):
    working = tmp_path / "readout.md"
    scratch = tmp_path / "scratch"
    for length in [maximum, maximum + 1]:
        text = "x" * length
        working.write_text(
            f"---\nformat: {fmt}\n---\n\n## Sources\n\n- [S1] Illustrative evidence.\n\n"
            '::: {#first .section intent="bullets"}\n## Evidence\n\n- Record the evidence.\n:::\n\n'
            '::: {#second .section intent="bullets"}\n## Next steps\n\n- Agree the next step.\n:::\n\n'
            f'::: {{#target .section intent="bullets"}}\n## Findings\n\n- {text} [S404]\n:::\n',
            encoding="utf-8",
        )
        built = api.build(working)
        preview = api.preview(working, scratch)
        assert main(["look", str(built.version), "--pages", "--json"]) == 0
        saved = json.loads(capsys.readouterr().out)
        assert [finding.model_dump(mode="json") for finding in preview.findings] == saved["findings"]
        assert [item.model_dump(mode="json") for item in preview.pages] == saved["pages"]
        relevant = [
            finding
            for finding in preview.findings
            if finding.rule_id in {"source.capacity", "source.unknown-citation", "source.citations-resolve"}
        ]
        assert {finding.rule_id for finding in relevant} == {
            "source.unknown-citation",
            "source.citations-resolve",
        } | ({"source.capacity"} if length > maximum else set())
        assert all(finding.page == page and finding.section_id == "target" for finding in relevant)
