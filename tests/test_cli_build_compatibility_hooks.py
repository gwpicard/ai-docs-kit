"""The shared build path retains the CLI's working-file and copy hooks."""

from pathlib import Path

import pytest

from ai_docs_kit import api, building, cli
from ai_docs_kit.source.read import read_source

ROOT = Path(__file__).resolve().parents[1]
BOM = b"\xef\xbb\xbf"


@pytest.fixture(params=["doc", "slides"])
def working_file(request, tmp_path):
    name = "report.md" if request.param == "doc" else "deck.md"
    path = tmp_path / name
    path.write_bytes(BOM + (ROOT / "tests" / "fixtures" / request.param / name).read_bytes())
    return path


def test_check_reads_through_the_cli_source_hook(working_file, monkeypatch, capsys):
    original = working_file.read_bytes()
    reads = []

    def read_working(path):
        text = read_source(path)
        assert not text.startswith("\ufeff")
        reads.append(path)
        return text

    monkeypatch.setattr(cli, "read_source", read_working, raising=False)
    code = cli.main(["check", str(working_file)])
    captured = capsys.readouterr()
    assert code in (0, 1) and not captured.err, captured
    assert reads == [working_file]
    assert working_file.read_bytes() == original


def test_build_writes_through_the_cli_copy_hook(working_file, monkeypatch, capsys):
    original = working_file.read_bytes()
    write_copy = getattr(cli, "_pptx", building._pptx)
    copies = []

    def write_review_copy(file, out, built, facts):
        copies.append(file)
        return write_copy(file, out, built, facts)

    monkeypatch.setattr(cli, "_pptx", write_review_copy, raising=False)
    code = cli.main(["build", str(working_file), "--json"])
    captured = capsys.readouterr()
    assert code == 0 and not captured.err, captured
    result = api.BuildResult.model_validate_json(captured.out)
    assert copies == [working_file]
    assert {output.suffix for output in result.outputs} == {
        ".pdf",
        ".docx" if api.read_document(working_file).format == "doc" else ".pptx",
    }
    assert all(output.is_file() for output in result.outputs)
    assert working_file.read_bytes() == original
