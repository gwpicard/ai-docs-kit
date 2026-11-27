"""Scratch previews preserve project state and refresh changed content."""

import shutil
from pathlib import Path

import pytest

from ai_docs_kit import api
from ai_docs_kit.loop import look

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("format,name", [("doc", "report.md"), ("slides", "deck.md")])
def test_preview_changes_refresh_facts_and_reject_project_state(tmp_path, capsys, monkeypatch, format, name):
    extract = look.layout_facts
    extracted = []

    def record_extraction(*args, **kwargs):
        facts = extract(*args, **kwargs)
        extracted.append(facts.pdf_sha256)
        return facts

    monkeypatch.setattr(look, "layout_facts", record_extraction)
    project = tmp_path / "project"
    project.mkdir()
    path = project / name
    shutil.copyfile(ROOT / "tests" / "fixtures" / format / name, path)
    scratch = project / "preview"
    first = api.preview(str(path), str(scratch))
    assert first.pngs and first.fields
    first_image = first.pngs[0].read_bytes()
    original = path.read_bytes()
    for forbidden in (project, path.with_suffix(".versions"), project / ".ai_docs_kit" / "preview"):
        with pytest.raises(ValueError, match="scratch must be separate"):
            api.preview(path, forbidden)
        assert path.read_bytes() == original
        assert not path.with_suffix(".versions").exists()
        assert not (project / ".ai_docs_kit").exists()
    title = api.read_document(path).sections[0].title
    assert title
    path.write_text(path.read_text().replace(f"## {title}", "## Updated preview title", 1))
    second = api.preview(path, scratch)
    assert second.pngs[0].read_bytes() != first_image
    assert len(extracted) == 2 and extracted[0] != extracted[1]
    # Section ids live in Typst marks, so a visually identical edit must also
    # refresh the region and field anchors returned by the public entry point.
    old_id = api.read_document(path).sections[0].id
    assert old_id
    path.write_text(path.read_text().replace(f"#{old_id} ", "#renamed-section ", 1))
    renamed = api.preview(path, scratch)
    assert "renamed-section" in renamed.pages[0].sections
    assert old_id not in {box.section for page in renamed.fields for box in page.fields}
    assert not path.with_suffix(".versions").exists()
    assert not (project / ".ai_docs_kit").exists()
    assert not capsys.readouterr().out
