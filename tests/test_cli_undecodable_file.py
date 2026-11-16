import pytest

from ai_docs_kit.cli import main


@pytest.mark.parametrize("command", ["build", "check"])
def test_undecodable_working_file_exits_two_with_a_message(tmp_path, capsys, command):
    file = tmp_path / "bad.md"
    file.write_bytes(b"\xff\xfe not utf-8")
    assert main([command, str(file)]) == 2
    assert "bad.md" in capsys.readouterr().err
