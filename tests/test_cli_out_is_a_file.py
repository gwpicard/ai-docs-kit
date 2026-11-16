from pathlib import Path

import pytest

from ai_docs_kit.cli import main

GALLERY = Path(__file__).parent / "fixtures" / "slides" / "gallery.md"


@pytest.mark.parametrize("command", ["build", "check"])
def test_out_that_is_a_file_exits_two_with_a_message(tmp_path, capsys, command):
    out = tmp_path / "out"
    out.write_text("not a folder")
    assert main([command, str(GALLERY), "--out", str(out)]) == 2
    assert "out" in capsys.readouterr().err
