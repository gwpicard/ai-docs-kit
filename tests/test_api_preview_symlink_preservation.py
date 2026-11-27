"""Preview refuses aliased version and state stores before writing anything."""

import hashlib
import shutil
from pathlib import Path

import pytest

from ai_docs_kit import api

ROOT = Path(__file__).resolve().parents[1]


def _snapshot(root):
    return {
        str(path.relative_to(root)): (
            path.is_dir(),
            path.stat().st_mtime_ns,
            None if path.is_dir() else hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in (root, *sorted(root.rglob("*")))
    }


@pytest.mark.parametrize("format,name", [("doc", "report.md"), ("slides", "deck.md")])
@pytest.mark.parametrize("working_alias", [False, True], ids=["working-file", "working-file-alias"])
def test_preview_preserves_symlinked_stores(tmp_path, format, name, working_alias):
    project = tmp_path / "project"
    project.mkdir()
    working = project / name
    source = tmp_path / "original.md" if working_alias else working
    shutil.copyfile(ROOT / "tests" / "fixtures" / format / name, source)
    if working_alias:
        working.symlink_to(source)

    stores = tmp_path / "saved stores"
    stores.mkdir()
    versions = stores / "render"
    versions.mkdir()
    versions_link = working.with_suffix(".versions")
    versions_link.symlink_to(versions, target_is_directory=True)
    state = stores / "look"
    state.mkdir()
    state_link = project / ".ai_docs_kit"
    state_link.symlink_to(state, target_is_directory=True)
    (state / "oplog.jsonl").write_bytes(b"")
    built = api.build(working)
    assert built.version == versions_link / "v1"
    saved_pdf = next(output for output in built.outputs if output.suffix == ".pdf")
    saved_bytes = saved_pdf.read_bytes()
    title = api.read_document(working).sections[0].title
    assert title
    source.write_text(source.read_text().replace(f"## {title}", "## Updated preview heading", 1))

    # A harmless scratch alias still works and renders the changed heading.
    scratch = tmp_path / "allowed scratch"
    scratch.mkdir()
    scratch_link = tmp_path / "scratch alias"
    scratch_link.symlink_to(scratch, target_is_directory=True)
    control = api.preview(working, scratch_link)
    assert control.pngs and all(image.is_file() for image in control.pngs)
    assert (scratch / f"{working.stem}.pdf").read_bytes() != saved_bytes

    roots = (project, versions, state, source)
    before = [_snapshot(root) for root in roots]
    for forbidden in (built.version, versions / "v1", state_link / "scratch", state / "scratch", stores):
        with pytest.raises(ValueError, match="scratch must be separate"):
            api.preview(working, forbidden)
        assert [_snapshot(root) for root in roots] == before
        assert saved_pdf.read_bytes() == saved_bytes
        assert not (versions / "v1" / "render").exists()
        assert not (versions / "v1" / "look").exists()
