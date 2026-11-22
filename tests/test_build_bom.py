from tests.support.fixtures import fixture_path

from ai_docs_kit.cli import main


def test_build_reads_a_file_saved_with_a_byte_order_mark(tmp_path, capsys):
    source = fixture_path("doc", "report.md").read_bytes()
    (tmp_path / "report.md").write_bytes(b"\xef\xbb\xbf" + source)
    code = main(["build", str(tmp_path / "report.md")])
    err = capsys.readouterr().err
    assert code == 0, err
    assert (tmp_path / "build" / "report.pdf").is_file()
