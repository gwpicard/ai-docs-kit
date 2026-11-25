"""Rule testing validates stored section props, including entries after its example."""

import json
import subprocess
import sys
from pathlib import Path

import pytest


def _run(*args):
    return subprocess.run(
        [str(Path(sys.executable).with_name("ai-docs-kit")), *map(str, args)],
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.mark.parametrize("position", ["selected", "later"])
@pytest.mark.parametrize("props", [7, True, "title"])
def test_rule_test_refuses_non_object_stored_props_cleanly(tmp_path, position, props):
    source = tmp_path / "note.md"
    source.write_text(
        "---\ndoctype: report\nformat: doc\ntitle: Note\n---\n\n"
        '::: {#timing .section intent="body"}\n## Timing\n\nReply ASAP about the plan.\n:::\n',
        encoding="utf-8",
    )
    built = _run("build", source)
    assert built.returncode == 0, built.stderr
    version = tmp_path / "note.versions" / "v1"
    rule = tmp_path / "rule.yaml"
    rule.write_text(
        "id: feedback.give-date\ntitle: Give a date\norigin: feedback\nstrength: soft\n"
        "status: proposed\nseverity: error\ntier: source\n"
        "check: {kind: text-pattern, field: paragraphs, regex: ASAP}\n"
        "remedy: {class: redraft, hint: Give a date.}\n"
        "provenance: {source: {comment: Give a date.}, by: Dana}\n",
        encoding="utf-8",
    )
    args = ("rule", "test", rule, "--example", f"{version}/timing")
    control = _run(*args)
    assert control.returncode == 0, control.stderr
    composition = version / "composition.json"
    saved = json.loads(composition.read_text(encoding="utf-8"))
    if position == "selected":
        saved["sections"][0]["props"] = props
    else:
        saved["sections"].append({**saved["sections"][0], "id": "other", "props": props})
    composition.write_text(json.dumps(saved), encoding="utf-8")
    before = composition.read_bytes(), source.read_bytes()

    result = _run(*args)

    assert result.returncode == 2, result.stderr or result.stdout
    assert "composition.json" in result.stderr
    assert "Traceback" not in result.stderr
    assert len(result.stderr.strip().splitlines()) == 1
    assert (composition.read_bytes(), source.read_bytes()) == before
