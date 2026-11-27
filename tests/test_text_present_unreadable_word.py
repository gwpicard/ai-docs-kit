"""Checking a damaged Word copy reports one diagnostic and preserves its bytes."""

from io import BytesIO
from zipfile import ZipFile

import pytest

from ai_docs_kit import cli


def _damage(contents, damage):
    if damage == "truncated":
        return contents[:40]
    result = BytesIO()
    with ZipFile(BytesIO(contents)) as source, ZipFile(result, "w") as target:
        for info in source.infolist():
            if info.filename == "word/document.xml" and damage == "missing-part":
                continue
            data = source.read(info)
            if info.filename == "word/document.xml" and damage == "invalid-xml":
                data = b"<document"
            if info.filename == "[Content_Types].xml" and damage == "wrong-type":
                data = data.replace(
                    b"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
                    b"application/xml",
                )
            target.writestr(info, data)
    return result.getvalue()


@pytest.mark.parametrize("damage", ["truncated", "invalid-xml", "missing-part", "wrong-type"])
def test_check_accepts_valid_word_then_refuses_corrupt_copy_without_replacing_it(tmp_path, capsys, damage):
    source = tmp_path / "report.md"
    source.write_text(
        '---\ndoctype: report\nformat: doc\n---\n\n::: {#access .section intent="body"}\n'
        "## Access findings\n\nThe register keeps each route under review.\n:::\n",
        encoding="utf-8",
    )
    assert cli.main(["build", str(source)]) == 0
    assert capsys.readouterr().err == ""
    copy = tmp_path / "build" / "report.docx"
    valid = copy.read_bytes()
    assert cli.main(["check", str(source)]) == 0
    assert capsys.readouterr().err == ""
    assert copy.read_bytes() == valid

    damaged = _damage(valid, damage)
    copy.write_bytes(damaged)
    assert cli.main(["check", str(source)]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert len(output.err.splitlines()) == 1, output.err
    assert str(copy) in output.err and "Word copy" in output.err, output.err
    assert "Traceback" not in output.err
    assert copy.read_bytes() == damaged
