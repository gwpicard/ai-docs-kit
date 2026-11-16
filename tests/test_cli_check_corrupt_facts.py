import shutil
from pathlib import Path

from ai_docs_kit.cli import main

GALLERY = Path(__file__).parent / "fixtures" / "slides" / "gallery.md"


def test_check_with_corrupt_source_facts_exits_two_with_a_message(tmp_path, capsys):
    file = tmp_path / "g.md"
    shutil.copy(GALLERY, file)
    facts = tmp_path / ".ai_docs_kit" / "write" / "g" / "facts.json"
    facts.parent.mkdir(parents=True)
    facts.write_text("{bad")
    assert main(["check", str(file)]) == 2
    assert "facts.json" in capsys.readouterr().err
