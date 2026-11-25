"""Damaged LZMA Office parts must produce a clean refusal and preserve the previous plan."""

import json
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from ai_docs_kit.cli import main


@pytest.mark.parametrize(
    ("suffix", "part"),
    [
        ("docx", "word/document.xml"),
        ("pptx", "ppt/presentation.xml"),
        ("docx", "docProps/custom.xml"),
        ("pptx", "docProps/custom.xml"),
    ],
)
def test_review_read_refuses_corrupt_lzma_parts(tmp_path: Path, suffix: str, part: str) -> None:
    source = tmp_path / "note.md"
    format_name, doctype, intent = (
        ("doc", "report", "body") if suffix == "docx" else ("slides", "pitch-deck", "statement")
    )
    source.write_text(
        f"---\ndoctype: {doctype}\nformat: {format_name}\ntitle: Note\n---\n\n"
        f'::: {{#alpha .section intent="{intent}"}}\n## The direction\n\n'
        "Keep the original wording.\n:::\n",
        encoding="utf-8",
    )
    assert main(["build", str(source)]) == 0
    version = tmp_path / "note.versions" / "v1"
    copy = tmp_path / f"note-reviewed.{suffix}"
    with zipfile.ZipFile(version / f"note.{suffix}") as original, zipfile.ZipFile(copy, "w") as archive:
        for name in original.namelist():
            compression = zipfile.ZIP_LZMA if name == part else zipfile.ZIP_DEFLATED
            archive.writestr(name, original.read(name), compress_type=compression)

    # The same real copy with intact LZMA data must remain readable.
    assert main(["review", "read", str(copy)]) == 0
    plan = version / "review-plan.json"
    before = plan.read_bytes()
    with zipfile.ZipFile(copy) as archive:
        info = archive.getinfo(part)
    data = bytearray(copy.read_bytes())
    name_length, extra_length = struct.unpack_from("<HH", data, info.header_offset + 26)
    start = info.header_offset + 30 + name_length + extra_length
    assert info.compress_size > 32
    data[start + 12 : start + 32] = b"\xff" * 20
    copy.write_bytes(data)

    result = subprocess.run(
        [sys.executable, "-m", "ai_docs_kit.cli", "review", "read", str(copy)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    # Corrupt optional properties may be ignored, as the existing metadata reader promises.
    allowed = {0, 2} if part == "docProps/custom.xml" else {2}
    assert result.returncode in allowed, result.stderr
    assert "Traceback" not in result.stderr
    if result.returncode == 2:
        assert len(result.stderr.strip().splitlines()) == 1
        assert copy.name in result.stderr
        assert plan.read_bytes() == before
    else:
        assert result.stderr == ""
        assert json.loads(plan.read_bytes())["confirm"] == []
