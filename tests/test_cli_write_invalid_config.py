from ai_docs_kit.cli import main


def test_write_with_an_invalid_config_exits_two_with_a_message(tmp_path, capsys):
    (tmp_path / "ai_docs_kit.toml").write_text("not [valid toml\n")
    source = tmp_path / "a.md"
    source.write_text("# T\n")
    assert main(["write", str(source)]) == 2
    assert "ai_docs_kit.toml" in capsys.readouterr().err
