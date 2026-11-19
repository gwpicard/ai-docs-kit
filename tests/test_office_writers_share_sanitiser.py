"""The Word and PowerPoint writers strip XML-illegal characters with one shared function."""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "ai_docs_kit"
ILLEGAL_RANGE = re.compile(r"\\ufffe|\\uffff|￾|￿", re.IGNORECASE)


def test_one_function_holds_the_illegal_character_set():
    holders = [p.name for p in SRC.rglob("*.py") if ILLEGAL_RANGE.search(p.read_text(encoding="utf-8"))]
    assert len(holders) == 1, f"the illegal-character set is spelled in {holders}"


def test_both_writers_call_a_sanitiser_they_do_not_define():
    (holder,) = [p for p in SRC.rglob("*.py") if ILLEGAL_RANGE.search(p.read_text(encoding="utf-8"))]
    for writer in ("word.py", "pptx_copy.py"):
        path = SRC / "render" / writer
        text = path.read_text(encoding="utf-8")
        if path != holder:
            assert f"from ai_docs_kit.{'.'.join(holder.relative_to(SRC).with_suffix('').parts)} import" in text, writer
