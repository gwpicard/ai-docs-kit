"""Text that XML cannot hold never crashes the Word or PowerPoint copy."""

import pytest
from docx import Document
from pptx import Presentation
from tests.support.fixtures import fixture_path

from ai_docs_kit.cli import main

BOM = b"\xef\xbb\xbf"
C0 = [chr(c) for c in range(0x20) if chr(c) not in "\t\n\r"]
ILLEGAL = [*C0, "\ud800", "￾", "￿"]
IDS = [f"U+{ord(c):04X}" for c in ILLEGAL]


def _spell(char: str) -> str:
    """A lone surrogate has no UTF-8 form, so a file can only carry it as a character reference."""
    return f"&#x{ord(char):X};" if "\ud800" <= char <= "\udfff" else char


def _write(path, text: str, bom: bool) -> None:
    data = text.encode("utf-8")
    path.write_bytes(BOM + data if bom else data)


def _doc(char: str) -> str:
    return (
        fixture_path("doc", "report.md")
        .read_text(encoding="utf-8")
        .replace("\n\n", f"\n\nBefore {_spell(char)} after.\n\n", 1)
    )


def _deck(char: str) -> str:
    text = fixture_path("slides", "deck.md").read_text(encoding="utf-8")
    return text.replace(
        "Simple ideas make a strong story.\n",
        f"Simple ideas {_spell(char)} make a strong story.\n> note: Say {_spell(char)} this.\n",
    )


@pytest.mark.parametrize("bom", [False, True], ids=["plain", "bom"])
@pytest.mark.parametrize("char", ILLEGAL, ids=IDS)
def test_word_copy_builds_and_reopens(tmp_path, capsys, char, bom):
    file = tmp_path / "report.md"
    _write(file, _doc(char), bom)
    code = main(["build", str(file)])
    err = capsys.readouterr().err
    assert code == 0, err
    Document(str(tmp_path / "build" / "report.docx"))


@pytest.mark.parametrize("bom", [False, True], ids=["plain", "bom"])
@pytest.mark.parametrize("char", ILLEGAL, ids=IDS)
def test_powerpoint_copy_builds_and_reopens(tmp_path, capsys, char, bom):
    file = tmp_path / "deck.md"
    _write(file, _deck(char), bom)
    try:
        code = main(["build", str(file)])
    except ValueError as error:
        raise AssertionError(f"the build raised instead of writing the copy: {error}") from error
    err = capsys.readouterr().err
    assert code == 0, err
    Presentation(str(tmp_path / "build" / "deck.pptx"))
