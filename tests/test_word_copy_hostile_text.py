"""The Word copy survives odd text and names that a source may carry."""

import zipfile

from lxml import etree

from ai_docs_kit.cli import main

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _source(section_id: str, body: str) -> str:
    return (
        "---\ndoctype: report\nformat: doc\ntitle: Odd\n---\n\n"
        f'::: {{#{section_id} .section intent="body"}}\n## Opening\n\n{body}\n:::\n'
    )


def _build(tmp_path, capsys, text: str):
    file = tmp_path / "odd.md"
    file.write_text(text, encoding="utf-8")
    code = main(["build", str(file)])
    capsys.readouterr()
    return code, tmp_path / "build" / "odd.docx"


def test_a_control_character_in_the_text_does_not_crash_the_word_copy(tmp_path, capsys):
    try:
        code, docx = _build(tmp_path, capsys, _source("s1", "Bell \x01 here."))
    except ValueError as error:
        raise AssertionError(f"the build raised instead of writing the copy: {error}") from error
    assert code == 0
    assert docx.is_file()


def test_bookmark_names_are_valid_in_word(tmp_path, capsys):
    """Word allows letters, digits and underscores, starting with a letter, at most 40 characters."""
    code, docx = _build(tmp_path, capsys, _source("my-section", "Body."))
    assert code == 0 and docx.is_file()
    with zipfile.ZipFile(docx) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    names = [n.get(f"{{{W}}}name") for n in root.iter(f"{{{W}}}bookmarkStart")]
    assert names
    for name in names:
        assert len(name) <= 40 and name[0].isalpha() and name.replace("_", "").isalnum(), name
