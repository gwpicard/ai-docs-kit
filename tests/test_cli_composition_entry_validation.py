"""A valid section cannot hide a malformed entry later in the stored composition."""

import json

import pytest

from ai_docs_kit.cli import main


@pytest.mark.parametrize("command", ["rule test", "review apply"])
@pytest.mark.parametrize("entry", [None, "interrupted section", []])
def test_commands_validate_entries_after_the_selected_section(tmp_path, capsys, command, entry):
    source = tmp_path / "note.md"
    source.write_text(
        "---\ndoctype: report\nformat: doc\ntitle: Timing\n---\n\n"
        '::: {#timing .section intent="body"}\n## Timing\n\nReply ASAP about the plan.\n:::\n',
        encoding="utf-8",
    )
    assert main(["build", str(source)]) == 0
    before = source.read_bytes()
    version = tmp_path / "note.versions" / "v1"
    composition = version / "composition.json"
    saved = json.loads(composition.read_text(encoding="utf-8"))
    saved["sections"].append(entry)
    composition.write_text(json.dumps(saved), encoding="utf-8")
    if command == "rule test":
        rule = tmp_path / "rule.yaml"
        rule.write_text(
            "id: feedback.give-date\ntitle: Give a date\norigin: feedback\nstrength: soft\n"
            "status: proposed\nseverity: error\ntier: source\n"
            "check: {kind: text-pattern, field: paragraphs, regex: ASAP}\n"
            "remedy: {class: redraft, hint: Give a date.}\n"
            "provenance: {source: {comment: Give a date.}, by: Dana}\n",
            encoding="utf-8",
        )
        args = ["rule", "test", str(rule), "--example", f"{version}/timing"]
    else:
        plan = tmp_path / "decided.json"
        plan.write_text(
            json.dumps(
                {
                    "version": 1,
                    "review_copy": "note-reviewed.docx",
                    "sections": {"timing": {"title": None, "wording": "Revised wording.", "owner": "human"}},
                }
            ),
            encoding="utf-8",
        )
        args = ["review", "apply", str(source), "--plan", str(plan)]
    capsys.readouterr()

    assert main(args) == 2

    output = capsys.readouterr()
    assert not output.out
    assert str(composition) in output.err
    assert "sections must be a list of objects" in output.err
    assert "Traceback" not in output.err
    assert len(output.err.strip().splitlines()) == 1
    assert source.read_bytes() == before
