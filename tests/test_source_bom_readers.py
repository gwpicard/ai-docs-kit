"""Every reader of a working file accepts a byte order mark; no read in `src` parses a raw read."""

import ast
import json
from pathlib import Path

from ai_docs_kit.cli import main
from ai_docs_kit.store.feedback import add_feedback, load_feedback

BOM = b"\xef\xbb\xbf"
SRC = Path(__file__).resolve().parent.parent / "src" / "ai_docs_kit"

FRONT = """---
doctype: report
format: doc
title: Note
---

"""

WORKING = """::: {#intro .section intent="body"}
## Introduction

The note opens here.
:::
"""


def _bom_file(tmp_path: Path, front: str = "") -> Path:
    # Without front matter the first line is a section block, so a kept BOM hides every section.
    path = tmp_path / "note.md"
    path.write_bytes(BOM + (front + WORKING).encode("utf-8"))
    return path


def test_a_comment_on_a_section_of_a_file_with_a_byte_order_mark(tmp_path):
    path = _bom_file(tmp_path)
    add_feedback(path, "Tighten this.", section_id="intro")
    assert [c.section_id for c in load_feedback(path)] == ["intro"]


def test_review_apply_reads_a_file_with_a_byte_order_mark(tmp_path, capsys):
    path = _bom_file(tmp_path, FRONT)
    plan = {
        "version": 1,
        "review_copy": "x.docx",
        "sections": {"intro": {"wording": "The note now opens differently.", "owner": "human"}},
    }
    decided = tmp_path / "decided.json"
    decided.write_text(json.dumps(plan), encoding="utf-8")
    code = main(["review", "apply", str(path), "--plan", str(decided)])
    assert code == 0, capsys.readouterr().err
    written = path.read_bytes()
    assert not written.startswith(BOM)
    assert b"The note now opens differently." in written


def _is_raw_read(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in ("read_text", "read_bytes")
        or isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "decode"
        and any(_is_raw_read(n) for n in ast.walk(node.func.value))
    )


def _contains_raw_read(node: ast.AST) -> bool:
    return any(_is_raw_read(n) for n in ast.walk(node))


def _offenders(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for scope in [tree, *(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef))]:
        raw = {
            target.id
            for n in ast.walk(scope)
            if isinstance(n, ast.Assign) and _contains_raw_read(n.value)
            for target in n.targets
            if isinstance(target, ast.Name)
        }
        for n in ast.walk(scope):
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "parse" and n.args:
                arg = n.args[0]
                if _contains_raw_read(arg) or any(isinstance(m, ast.Name) and m.id in raw for m in ast.walk(arg)):
                    found.append(f"{path.relative_to(SRC)}:{n.lineno}")
    return sorted(set(found))


def test_no_parse_in_src_is_fed_by_a_raw_read():
    offenders = [
        o
        for path in SRC.rglob("*.py")
        if path.name != "read.py" or path.parent.name != "source"
        for o in _offenders(path)
    ]
    assert offenders == []
