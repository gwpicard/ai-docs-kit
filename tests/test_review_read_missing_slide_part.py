"""A missing referenced slide is archive damage, not a reviewer's request to delete a section."""

import json
import zipfile
from pathlib import Path

from ai_docs_kit.cli import main


def test_review_read_refuses_a_missing_referenced_slide(tmp_path: Path, capsys) -> None:
    source = tmp_path / "note.md"
    source.write_text(
        "---\ndoctype: pitch-deck\nformat: slides\ntitle: Note\n---\n\n"
        '::: {#alpha .section intent="statement"}\n## The direction\n\n'
        "Keep the original wording.\n:::\n",
        encoding="utf-8",
    )
    assert main(["build", str(source)]) == 0
    version = tmp_path / "note.versions" / "v1"
    original = version / "note.pptx"
    copy = tmp_path / "note-reviewed.pptx"
    copy.write_bytes(original.read_bytes())
    assert main(["review", "read", str(copy)]) == 0
    plan = version / "review-plan.json"
    before = plan.read_bytes()
    assert json.loads(before)["confirm"] == []

    # Leave the slide id and its relationship intact, as in an interrupted archive rewrite.
    with zipfile.ZipFile(original) as archive, zipfile.ZipFile(copy, "w", zipfile.ZIP_DEFLATED) as target:
        assert "ppt/slides/slide1.xml" in archive.namelist()
        for name in archive.namelist():
            if name != "ppt/slides/slide1.xml":
                target.writestr(name, archive.read(name))
    capsys.readouterr()
    code = main(["review", "read", str(copy)])
    output = capsys.readouterr()
    assert code == 2, f"A broken slide reference was accepted as a deletion: {plan.read_text()}"
    assert "Traceback" not in output.err
    assert len(output.err.strip().splitlines()) == 1
    assert copy.name in output.err
    assert plan.read_bytes() == before
