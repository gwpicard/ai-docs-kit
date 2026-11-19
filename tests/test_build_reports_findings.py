"""Build reports recorded errors and gaps without failing an ordinary build."""

import json

import pytest

from ai_docs_kit.cli import main


@pytest.mark.parametrize("format_, intent", [("slides", "bullets"), ("doc", "callout")])
@pytest.mark.parametrize(
    "text, has_error, has_gap",
    [
        ("Confirm the date. [S9 p.4]", True, False),
        ("Confirm [GAP: the agreed date].", False, True),
        ("Confirm [GAP: the agreed date]. [S9 p.4]", True, True),
        ("Confirm the date.", False, False),
    ],
)
def test_build_reports_recorded_errors_and_gaps(tmp_path, capsys, format_, intent, text, has_error, has_gap):
    source = tmp_path / "timing.md"
    content = f"- {text}\n- Record the decision.\n- Check the scope."
    source.write_text(
        f"---\nformat: {format_}\ntitle: Timing\n---\n\n"
        f'::: {{#timing .section intent="{intent}"}}\n## Timing\n\n{content}\n:::\n',
        encoding="utf-8",
    )

    assert main(["build", str(source)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    lines = captured.out.splitlines()
    version = tmp_path / "timing.versions" / "v1"
    assert lines[0] == str(tmp_path / "build" / "timing.pdf")
    assert lines[-1] == str(version)
    findings = json.loads((version / "findings.json").read_text(encoding="utf-8"))
    manifest = json.loads((version / "manifest.json").read_text(encoding="utf-8"))
    errors = [finding for finding in findings if finding["severity"] == "error"]
    assert bool(errors) is has_error
    assert bool(manifest["gaps"]) is has_gap
    expected = [f"error {f['rule_id']} {f['section_id'] or '-'} {f['message']}" for f in errors]
    expected += [f"gap {gap['section'] or '-'}: {gap['text']}" for gap in manifest["gaps"]]
    assert lines[1:-1] == expected
