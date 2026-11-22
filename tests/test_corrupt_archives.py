"""Every reader of an outside Office archive turns a corrupt file into a clean refusal, never a traceback."""

import inspect
import json
import struct
import zipfile
from pathlib import Path

import pytest

from ai_docs_kit.brand import templates
from ai_docs_kit.cli import main
from ai_docs_kit.review import pptx_read, word_read

TYPES = (
    '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="xml" ContentType="application/xml"/></Types>'
)
MAIN_PART = {".docx": "word/document.xml", ".pptx": "ppt/presentation.xml"}
RELS = "_rels/.rels"
KINDS = ["truncated-zip", "bad-deflate", "malformed-xml"]


def _write(path: Path, kind: str, part: str | None = None) -> None:
    """Write an Office-named archive broken in the way `kind` names, in `part` (the main part by default)."""
    part = part or MAIN_PART[path.suffix]
    body = "<a>" + "x" * 5000 + "</a>"
    if kind == "malformed-xml":
        body = "<a><b></a>"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", TYPES)
        archive.writestr("docProps/app.xml", "<Properties/>")
        archive.writestr(part, body)
        if part != RELS:
            archive.writestr(RELS, "<Relationships/>")
    data = bytearray(path.read_bytes())
    if kind == "truncated-zip":
        path.write_bytes(bytes(data[: len(data) // 2]))
    elif kind == "bad-deflate":
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo(part)
        start = info.header_offset
        name, extra = struct.unpack("<HH", data[start + 26 : start + 30])
        body_at = start + 30 + name + extra
        data[body_at : body_at + 20] = b"\xff" * 20
        path.write_bytes(bytes(data))


def _one_line(text: str) -> None:
    assert text.strip()
    assert "Traceback" not in text
    assert len(text.strip().splitlines()) == 1, text


def _brand(tmp_path: Path, name: str, kind: str, part: str | None = None) -> Path:
    root = tmp_path / "brands"
    assert main(["brand", "init", "acme", "--root", str(root)]) == 0
    brand = root / "acme"
    _write(brand / "materials" / "templates" / name, kind, part)
    return brand


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("name", ["copy.docx", "copy.pptx"])
def test_review_read_refuses_a_corrupt_copy(tmp_path: Path, capsys, name: str, kind: str) -> None:
    work = tmp_path / "w"
    (work / "copy.versions" / "v1").mkdir(parents=True)
    _write(work / name, kind)
    capsys.readouterr()
    assert main(["review", "read", str(work / name)]) == 2
    out = capsys.readouterr()
    _one_line(out.err)
    assert "Traceback" not in out.out


@pytest.mark.parametrize("part", [None, RELS])
@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("name", ["deck.pptx", "report.docx"])
def test_brand_intake_and_templates_refuse_a_corrupt_file(
    tmp_path: Path, capsys, name: str, kind: str, part: str | None
) -> None:
    brand = _brand(tmp_path, name, kind, part)
    capsys.readouterr()
    code = main(["brand", "intake", "acme", "--root", str(brand.parent)])
    out = capsys.readouterr()
    assert "Traceback" not in out.out + out.err
    manifest = json.loads(next(brand.rglob("manifest.json")).read_text())
    entry = next(e for e in manifest["files"] if e["path"].endswith(name))
    if entry.get("unread"):
        _one_line(entry["unread"])
        return
    assert code == 0
    code = main(["brand", "templates", "acme", "--root", str(brand.parent)])
    out = capsys.readouterr()
    assert "Traceback" not in out.out + out.err
    assert code == 2
    lines = [line for line in out.out.splitlines() if "unread:" in line]
    assert len(lines) == 1, out.out
    assert name in lines[0]


def test_archive_errors_is_one_tuple_beside_check_archive() -> None:
    errors = word_read.ARCHIVE_ERRORS
    assert isinstance(errors, tuple)
    import zlib

    assert set(errors) == {
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
        EOFError,
        NotImplementedError,
        RuntimeError,
        zlib.error,
    }
    assert pptx_read.ARCHIVE_ERRORS is errors
    assert templates.ARCHIVE_ERRORS is errors


@pytest.mark.parametrize("module", [word_read, pptx_read, templates])
def test_no_reader_keeps_its_own_list(module) -> None:
    source = inspect.getsource(module)
    if module is word_read:
        assert source.count("LargeZipFile") == 1
    else:
        assert "LargeZipFile" not in source
        assert "ARCHIVE_ERRORS" in source
