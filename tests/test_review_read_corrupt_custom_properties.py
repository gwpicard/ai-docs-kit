"""A copy whose custom properties part is corrupt is read without them, never with a traceback."""

import struct
import zipfile
from pathlib import Path

import pytest

from ai_docs_kit.store.stamp import read_custom_properties, read_version_property

CUSTOM = "docProps/custom.xml"


def _corrupt(path: Path) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(CUSTOM, "<Properties>" + "x" * 5000 + "</Properties>")
    data = bytearray(path.read_bytes())
    with zipfile.ZipFile(path) as archive:
        start = archive.getinfo(CUSTOM).header_offset
    name, extra = struct.unpack("<HH", data[start + 26 : start + 30])
    at = start + 30 + name + extra
    data[at : at + 20] = b"\xff" * 20
    path.write_bytes(bytes(data))


@pytest.mark.parametrize("suffix", [".docx", ".pptx"])
def test_corrupt_custom_properties_read_as_none(tmp_path: Path, suffix: str) -> None:
    copy = tmp_path / f"copy{suffix}"
    _corrupt(copy)
    assert read_custom_properties(copy) == {}
    assert read_version_property(copy) is None
