"""`section put --redraft-done` writes a default because= when the new section has none."""

from pathlib import Path

from ai_docs_kit.cli import main

HEAD = (
    "---\ndoctype: report\nformat: doc\ntitle: Quarterly note\n---\n\n"
    "## Sources\n\n- [S1] Revenue was 120 in 2024 and 150 in 2025.\n\n"
)
BODY = "## Introduction\n\nRevenue grew from 120 to 150.\n:::\n"


def _run(tmp_path: Path, old_because: str, new_because: str) -> tuple[int, str]:
    path = tmp_path / "note.md"
    path.write_text(
        HEAD + f'::: {{#intro .section intent="opening" owner="ai" redraft="shorten this"{old_because}}}\n' + BODY
    )
    source = tmp_path / "new.md"
    source.write_text(f'::: {{#intro .section intent="opening" owner="ai"{new_because}}}\n' + BODY)
    code = main(["section", "put", str(path), "intro", "--from", str(source), "--redraft-done"])
    return code, path.read_text()


def _parses(tmp_path: Path) -> None:
    assert main(["section", "list", str(tmp_path / "note.md")]) == 0


def test_neither_has_because_writes_the_default(tmp_path):
    code, text = _run(tmp_path, "", "")
    assert code == 0
    assert "redraft=" not in text
    assert 'because="redrafted: shorten this"' in text
    _parses(tmp_path)


def test_new_because_is_kept(tmp_path):
    code, text = _run(tmp_path, "", ' because="Cut to one sentence."')
    assert code == 0
    assert 'because="Cut to one sentence."' in text
    assert "redrafted:" not in text
    _parses(tmp_path)


def test_only_old_because_is_replaced_by_the_default(tmp_path):
    code, text = _run(tmp_path, ' because="Old reason."', "")
    assert code == 0
    assert "Old reason." not in text
    assert 'because="redrafted: shorten this"' in text
    assert "redraft=" not in text
    _parses(tmp_path)
