"""A review copy whose compressed data is corrupt is refused with a message, not a traceback."""

import struct
import zipfile
from pathlib import Path

import pytest

from ai_docs_kit.review.pptx_read import read_deck
from ai_docs_kit.review.word_read import read_word


def _corrupt(path: Path, part: str, xml: str) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(part, xml)
    data = bytearray(path.read_bytes())
    start = data.find(b"PK\x03\x04")
    name, extra = struct.unpack("<HH", data[start + 26 : start + 30])
    body = start + 30 + name + extra
    data[body : body + 20] = b"\xff" * 20
    path.write_bytes(bytes(data))


def test_word_corrupt_deflate_is_a_value_error(tmp_path: Path) -> None:
    copy = tmp_path / "copy.docx"
    _corrupt(copy, "word/document.xml", "<a>" + "x" * 5000 + "</a>")
    with pytest.raises(ValueError):
        read_word(copy)


def test_deck_corrupt_deflate_is_a_value_error(tmp_path: Path) -> None:
    copy = tmp_path / "copy.pptx"
    _corrupt(copy, "ppt/presentation.xml", "<a>" + "x" * 5000 + "</a>")
    with pytest.raises(ValueError):
        read_deck(copy)
