"""Facts commands refuse bad input and keep each working file's evidence separate."""

import json

import pytest

from ai_docs_kit.cli import main

WORKING = """---
doctype: report
format: doc
title: Survey
---

## Sources

- [S1] survey.csv, table

::: {#results .section intent="body"}
## Results
:::
"""
FACT = {"text": "The survey counted 823 vessels.", "source": "S1", "answers": "fleet size"}
BLOCK = '::: {#results .section intent="body"}\n## Results\n\nThe survey counted 823 vessels. [S1]\n:::\n'
BAD_INPUTS = [
    b"",
    b"[",
    b"{}",
    b"null",
    b"[null]",
    b"[{}]",
    b'[{"text": "counted 823"}]',
    b'[{"text": 823, "source": "S1"}]',
    b'[{"text": " \\n", "source": "S1"}]',
    b'[{"text": "counted 823", "source": " "}]',
    b'[{"text": "counted 823", "source": "S1", "locator": " "}]',
    b'[{"text": "\xff", "source": "S1"}]',
]


def _seed(tmp_path):
    working = tmp_path / "report.md"
    working.write_text(WORKING, encoding="utf-8")
    incoming = tmp_path / "incoming.json"
    incoming.write_text(json.dumps([FACT]), encoding="utf-8")
    return working, incoming


def _refused(argv, capsys, path):
    assert main([str(arg) for arg in argv]) == 2
    out, err = capsys.readouterr()
    assert not out
    assert len(err.splitlines()) == 1
    assert str(path) in err
    assert "Traceback" not in err


@pytest.mark.parametrize("payload", BAD_INPUTS)
def test_bad_facts_input_leaves_existing_facts_unchanged(tmp_path, capsys, payload):
    working, incoming = _seed(tmp_path)
    assert main(["facts", "add", str(working), str(incoming)]) == 0
    capsys.readouterr()
    assert main(["facts", "list", str(working)]) == 0
    before = capsys.readouterr().out
    incoming.write_bytes(payload)

    _refused(["facts", "add", working, incoming], capsys, incoming)

    assert main(["facts", "list", str(working)]) == 0
    assert capsys.readouterr().out == before
    assert working.read_text(encoding="utf-8") == WORKING


@pytest.mark.parametrize("command", ["add", "list", "put"])
@pytest.mark.parametrize("payload", [b"{", b"{}", b"[null]", b'[{}, {"text": "x", "source": "S1"}]'])
def test_bad_stored_facts_are_refused_before_writing(tmp_path, capsys, command, payload):
    working, incoming = _seed(tmp_path)
    assert main(["facts", "add", str(working), str(incoming)]) == 0
    capsys.readouterr()
    store = next((tmp_path / ".ai_docs_kit" / "facts").iterdir())
    store.write_bytes(payload)
    if command == "put":
        block = tmp_path / "block.md"
        block.write_text(BLOCK, encoding="utf-8")
        argv = ["section", "put", working, "results", "--from", block]
    else:
        argv = ["facts", command, working] + ([incoming] if command == "add" else [])

    _refused(argv, capsys, store)

    assert store.read_bytes() == payload
    assert working.read_text(encoding="utf-8") == WORKING


def test_facts_do_not_leak_to_another_working_file(tmp_path, capsys):
    working, incoming = _seed(tmp_path)
    other = tmp_path / "other.md"
    other.write_text(WORKING, encoding="utf-8")
    assert main(["facts", "list", str(working)]) == 0
    assert capsys.readouterr().out == ""
    assert not (tmp_path / ".ai_docs_kit").exists()
    assert main(["facts", "add", str(working), str(incoming)]) == 0
    capsys.readouterr()
    assert main(["facts", "list", str(other)]) == 0
    assert capsys.readouterr().out == ""
    block = tmp_path / "block.md"
    block.write_text(BLOCK, encoding="utf-8")

    assert main(["section", "put", str(other), "results", "--from", str(block)]) == 1
    assert "823" in capsys.readouterr().err
    assert other.read_text(encoding="utf-8") == WORKING
    assert main(["section", "put", str(working), "results", "--from", str(block)]) == 0


def test_unknown_source_refuses_the_entire_batch(tmp_path, capsys):
    working, incoming = _seed(tmp_path)
    incoming.write_text(json.dumps([FACT, {**FACT, "source": "S99"}]), encoding="utf-8")

    _refused(["facts", "add", working, incoming], capsys, incoming)

    assert main(["facts", "list", str(working)]) == 0
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("directory", [False, True])
def test_unreadable_input_is_a_one_line_refusal(tmp_path, capsys, directory):
    working, incoming = _seed(tmp_path)
    incoming.unlink()
    if directory:
        incoming.mkdir()
    _refused(["facts", "add", working, incoming], capsys, incoming)


def test_blocked_store_is_a_one_line_refusal(tmp_path, capsys):
    working, incoming = _seed(tmp_path)
    store = tmp_path / ".ai_docs_kit"
    store.write_text("keep this file", encoding="utf-8")

    _refused(["facts", "add", working, incoming], capsys, store)

    assert store.read_text(encoding="utf-8") == "keep this file"


def test_list_keeps_a_multiline_fact_on_one_line(tmp_path, capsys):
    working, incoming = _seed(tmp_path)
    incoming.write_text(json.dumps([{**FACT, "text": "The survey\ncounted 823 vessels."}]), encoding="utf-8")
    assert main(["facts", "add", str(working), str(incoming)]) == 0
    capsys.readouterr()

    assert main(["facts", "list", str(working)]) == 0
    assert capsys.readouterr().out == "[S1] The survey counted 823 vessels.\n"
