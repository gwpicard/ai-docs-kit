"""Refuse a damaged deck even when other referenced slides remain readable."""

import json
import zipfile
from pathlib import Path

import pytest

from ai_docs_kit.cli import main


@pytest.mark.parametrize(
    ("sections", "missing_part"),
    [
        (("alpha", "beta", "gamma"), "ppt/slides/slide2.xml"),
        (("gamma", "beta", "alpha"), "ppt/slides/slide3.xml"),
    ],
)
def test_review_read_preserves_plan_when_a_later_slide_is_missing(
    tmp_path: Path, capsys, sections: tuple[str, ...], missing_part: str
) -> None:
    source = tmp_path / "note.md"
    source.write_text(
        "---\ndoctype: pitch-deck\nformat: slides\ntitle: Note\n---\n\n"
        + "\n".join(
            f'::: {{#{section} .section intent="statement"}}\n'
            f"## The {section} direction\n\nKeep the {section} wording.\n:::\n"
            for section in sections
        ),
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
    clean_plan = json.loads(before)
    assert clean_plan["confirm"] == []
    assert set(clean_plan["sections"]) == set(sections)

    # Retain the presentation's slide ids and relationships, and all other parts.
    with zipfile.ZipFile(original) as archive, zipfile.ZipFile(copy, "w", zipfile.ZIP_DEFLATED) as target:
        slide_parts = {
            name for name in archive.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        }
        assert len(slide_parts) == 3
        assert missing_part in slide_parts
        for name in archive.namelist():
            if name != missing_part:
                target.writestr(name, archive.read(name))
    damaged_copy = copy.read_bytes()
    working_file = source.read_bytes()
    capsys.readouterr()

    code = main(["review", "read", str(copy)])
    output = capsys.readouterr()

    assert code == 2, f"Missing {missing_part} was accepted: {plan.read_text(encoding='utf-8')}"
    assert "Traceback" not in output.err
    assert len(output.err.strip().splitlines()) == 1
    assert copy.name in output.err
    assert plan.read_bytes() == before
    assert copy.read_bytes() == damaged_copy
    assert source.read_bytes() == working_file
