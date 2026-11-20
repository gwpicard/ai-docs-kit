"""Build findings and look records use the current, validated source evidence."""

import json

import pytest

from ai_docs_kit.cli import main


@pytest.mark.parametrize("format_, intent", [("slides", "bullets"), ("doc", "callout")])
def test_build_refreshes_evidence_and_records_number_errors(tmp_path, capsys, format_, intent):
    source = tmp_path / "readings.md"
    source.write_text(
        f"---\nformat: {format_}\ntitle: Readings\n---\n\n"
        "## Sources\n\n- [S1] readings.csv\n\n"
        f'::: {{#reading .section intent="{intent}"}}\n## Readings\n\n'
        "- The reading was 19. [S1]\n- Record the date.\n- Confirm the scope.\n:::\n",
        encoding="utf-8",
    )
    stored = tmp_path / ".ai_docs_kit" / "write" / source.stem / "facts.json"
    checked = tmp_path / "checked"
    for version, (facts, expected_errors) in enumerate(
        [
            (None, 0),
            ([{"text": "The reading was 12.", "source_key": "S1"}], 1),
            ([{"text": "The reading was 19.", "source_key": "S1"}], 0),
            ([], 1),
        ],
        start=1,
    ):
        if facts is not None:
            stored.parent.mkdir(parents=True, exist_ok=True)
            stored.write_text(json.dumps(facts), encoding="utf-8")
        assert main(["check", str(source), "--out", str(checked)]) == int(bool(expected_errors))
        reported = json.loads((checked / "readings.findings.json").read_text(encoding="utf-8"))
        assert len(reported) == expected_errors
        capsys.readouterr()

        assert main(["build", str(source)]) == 0
        output = capsys.readouterr()
        folder = tmp_path / "readings.versions" / f"v{version}"
        built = json.loads((folder / "findings.json").read_text(encoding="utf-8"))
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        assert built == reported
        assert manifest["findings"]["error"] == expected_errors
        assert manifest["look"]["clean"] is (expected_errors == 0)
        assert ("error source.number-in-source reading" in output.out) is bool(expected_errors)
        assert output.out.splitlines()[-1] == str(folder)
        assert output.err == ""


@pytest.mark.parametrize("command", ["check", "build"])
@pytest.mark.parametrize("payload", [b"{", b"[{}]", b'[{"text":"\xc3'])
def test_build_and_check_refuse_invalid_evidence(tmp_path, capsys, command, payload):
    source = tmp_path / "readings.md"
    source.write_text(
        "---\nformat: slides\ntitle: Readings\n---\n\n"
        '::: {#reading .section intent="bullets"}\n## Readings\n\n- Confirm the scope.\n:::\n',
        encoding="utf-8",
    )
    stored = tmp_path / ".ai_docs_kit" / "write" / source.stem / "facts.json"
    stored.parent.mkdir(parents=True)
    stored.write_bytes(payload)

    assert main([command, str(source)]) == 2
    captured = capsys.readouterr()
    assert captured.err.startswith(f"{stored}: not valid facts (")
    assert len(captured.err.splitlines()) == 1
    assert not (tmp_path / "readings.versions").exists()
