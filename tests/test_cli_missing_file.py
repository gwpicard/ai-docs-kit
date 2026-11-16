import pytest

from ai_docs_kit.cli import main


@pytest.mark.parametrize("command", ["build", "check", "write"])
def test_missing_working_file_exits_two_with_a_message(tmp_path, capsys, command):
    missing = tmp_path / "nope.md"
    assert main([command, str(missing)]) == 2
    assert "nope.md" in capsys.readouterr().err
