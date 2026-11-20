"""Bookmark names live in a neutral module; every name is valid in Word, however long or odd the id."""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "ai_docs_kit"
IDS = ["beta01", "my-section", "a_b", "_x2d_", "1st", "Xenc_a", "Xenc_x", "é", "a" * 41, "é" * 10, "Xh_abc", "a" * 40]


def _names():
    from ai_docs_kit.bookmark_names import bookmark_name, section_of

    return bookmark_name, section_of


@pytest.mark.parametrize("section_id", IDS)
def test_every_name_is_valid_in_word(section_id):
    bookmark_name, _ = _names()
    name = bookmark_name(section_id)
    assert len(name) <= 40, name
    assert name[0].isascii() and name[0].isalpha(), name
    assert name.replace("_", "").isascii() and name.replace("_", "").isalnum(), name


@pytest.mark.parametrize("section_id", ["beta01", "my-section", "a_b", "1st", "Xenc_x", "é", "é" * 3])
def test_a_name_that_fits_maps_back_without_a_stored_map(section_id):
    bookmark_name, section_of = _names()
    assert section_of(bookmark_name(section_id)) == section_id


def test_a_valid_id_is_kept_as_it_is():
    bookmark_name, _ = _names()
    assert bookmark_name("beta01") == "beta01"


@pytest.mark.parametrize("section_id", ["a" * 41, "é" * 10, "x-" * 30])
def test_an_id_whose_encoding_is_too_long_gets_a_hashed_name(section_id):
    bookmark_name, _ = _names()
    name = bookmark_name(section_id)
    assert name.startswith("Xh_")
    assert bookmark_name(section_id) == name


def test_different_long_ids_get_different_hashed_names():
    bookmark_name, _ = _names()
    assert bookmark_name("a" * 41) != bookmark_name("a" * 42)


def test_render_imports_nothing_from_review():
    found = []
    for path in sorted((SRC / "render").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            modules = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom) and node.level == 0
                else []
            )
            found += [
                f"{path.name}: {m}" for m in modules if m == "ai_docs_kit.review" or m.startswith("ai_docs_kit.review.")
            ]
    assert not found, found
