"""An empty JSON object or string cannot silently erase the engine findings."""

import json

import pytest

from ai_docs_kit.cli import main


@pytest.mark.parametrize("damaged", [{}, ""])
def test_look_pages_refuses_non_array_engine_findings(tmp_path, capsys, damaged):
    source = tmp_path / "note.md"
    source.write_text(
        "---\ndoctype: report\nformat: doc\ntitle: Timing\n---\n\n"
        '::: {#timing .section intent="callout"}\n## Timing\n\n- Reply about the plan. [S9]\n:::\n',
        encoding="utf-8",
    )
    assert main(["build", str(source)]) == 0
    version = tmp_path / "note.versions" / "v1"
    assert main(["look", str(version), "--pages"]) == 0
    assert "source.citations-resolve" in capsys.readouterr().out
    manifest = version / "manifest.json"
    before = manifest.read_bytes()
    findings = version / "findings.json"
    findings.write_text(json.dumps(damaged), encoding="utf-8")

    code = main(["look", str(version), "--pages"])

    captured = capsys.readouterr()
    assert code == 2, captured.out + captured.err
    assert "findings.json" in captured.err
    assert len(captured.err.strip().splitlines()) == 1
    assert manifest.read_bytes() == before
