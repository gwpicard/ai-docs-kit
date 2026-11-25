"""A failed working-file replacement must not advance review history."""

import json
import os

from ai_docs_kit.cli import main


def test_failed_replace_keeps_history_and_allows_retry(tmp_path, monkeypatch, capsys):
    source = tmp_path / "note.md"
    source.write_text(
        "---\ndoctype: report\nformat: doc\ntitle: Note\n---\n\n"
        '::: {#timing .section intent="body"}\n## Timing\n\nReply about the plan.\n:::\n',
        encoding="utf-8",
    )
    assert main(["build", str(source)]) == 0
    plan = {
        "version": 1,
        "review_copy": "note-reviewed.docx",
        "sections": {"timing": {"wording": "The first revision.", "owner": "human"}},
    }
    decided = tmp_path / "decided.json"
    decided.write_text(json.dumps(plan), encoding="utf-8")
    args = ["review", "apply", str(source), "--plan", str(decided)]
    assert main(args) == 0
    history = tmp_path / ".ai_docs_kit" / "oplog.jsonl"
    before_source, before_history = source.read_bytes(), history.read_bytes()
    plan["sections"]["timing"]["wording"] = "The second revision."
    decided.write_text(json.dumps(plan), encoding="utf-8")

    replace = os.replace

    def fail_replace(src, dst):
        if dst == source:
            raise OSError(f"{source}: simulated replacement failure")
        return replace(src, dst)

    capsys.readouterr()
    with monkeypatch.context() as patch:
        patch.setattr(os, "replace", fail_replace)
        assert main(args) == 2
    error = capsys.readouterr().err
    assert str(source) in error and "Traceback" not in error
    assert source.read_bytes() == before_source
    assert history.read_bytes() == before_history
    assert not list(tmp_path.glob(".note.md.*.tmp"))

    assert main(args) == 0
    entries = [json.loads(line) for line in history.read_text(encoding="utf-8").splitlines()]
    assert [entry["rev"] for entry in entries] == [1, 2]
    assert "The second revision." in source.read_text(encoding="utf-8")
    assert "The first revision." in json.dumps(entries[-1]["inverse"])
