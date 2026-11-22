"""Every command that reads a working file accepts a UTF-8 byte order mark and never writes one."""

import re
from pathlib import Path

import pytest

from ai_docs_kit.cli import main

BOM = b"\xef\xbb\xbf"

WORKING = """---
doctype: report
format: doc
title: Quarterly note
---

## Sources

- [S1] Revenue was 120 in 2024 and 150 in 2025.

::: {#intro .section intent="opening" owner="ai"}
## Introduction

Revenue grew from 120 to 150.
:::

::: {#findings .section intent="evidence"}
## Findings

- **Growth** Revenue reached 150 in 2025. [S1]
:::
"""

REPLACEMENT = """::: {#intro .section intent="opening" owner="ai"}
## Introduction

Revenue reached 150 in 2025. [S1]
:::
"""


def _bom_file(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_bytes(BOM + text.encode("utf-8"))
    return path


def test_section_list_reads_a_file_with_a_byte_order_mark(tmp_path, capsys):
    path = _bom_file(tmp_path, "note.md", WORKING)
    assert main(["section", "list", str(path)]) == 0
    out = capsys.readouterr().out
    assert "intro" in out and "findings" in out


def test_section_get_reads_a_file_with_a_byte_order_mark(tmp_path, capsys):
    path = _bom_file(tmp_path, "note.md", WORKING)
    assert main(["section", "get", str(path), "intro"]) == 0
    assert "Revenue grew from 120 to 150." in capsys.readouterr().out


def test_section_put_succeeds_on_a_file_with_a_byte_order_mark_and_writes_none(tmp_path, capsys):
    path = _bom_file(tmp_path, "note.md", WORKING)
    new = _bom_file(tmp_path, "new.md", REPLACEMENT)
    code = main(["section", "put", str(path), "intro", "--from", str(new)])
    assert code == 0, capsys.readouterr().err
    written = path.read_bytes()
    assert not written.startswith(BOM)
    assert b"Revenue reached 150 in 2025." in written
    assert b"Revenue grew from 120 to 150." not in written


def test_write_outline_succeeds_on_a_file_with_a_byte_order_mark_and_writes_none(tmp_path, capsys):
    path = _bom_file(tmp_path, "note.md", WORKING)
    code = main(["write", str(path)])
    assert code == 0, capsys.readouterr().err
    assert not path.read_bytes().startswith(BOM)


def test_the_helper_reads_with_utf_8_sig(tmp_path):
    from ai_docs_kit.source import read_source

    path = _bom_file(tmp_path, "note.md", "héllo")
    assert read_source(path) == "héllo"


SRC = Path(__file__).resolve().parent.parent / "src" / "ai_docs_kit"


@pytest.mark.parametrize("name", ["cli.py", "write.py", "section_command.py", "evals/heal.py"])
def test_working_file_readers_use_the_helper(name):
    text = (SRC / name).read_text(encoding="utf-8")
    assert "read_source(" in text


def test_no_working_file_is_parsed_from_a_raw_read():
    pattern = re.compile(r"parse\(.*(read_text|read_bytes)")
    offenders = [
        f"{path.relative_to(SRC)}:{n}"
        for path in (
            SRC / name for name in ("cli.py", "write.py", "section_command.py", "evals/heal.py", "source/files.py")
        )
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if pattern.search(line)
    ]
    assert offenders == []
