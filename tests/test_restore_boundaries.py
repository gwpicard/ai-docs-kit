"""Restore uses reversible patches even at section and document boundaries."""

import json

import pytest

from ai_docs_kit import api, cli
from ai_docs_kit.model import Document, Section, Source
from ai_docs_kit.source.patches import PatchRejected
from ai_docs_kit.source.serialiser import serialise


def _setup(root, sections):
    path = root / "note.md"
    doc = Document(front={"format": "doc", "doctype": "report"}, format="doc", sections=sections)
    path.write_text(serialise(doc), encoding="utf-8")
    folder = path.with_suffix(".versions") / "v1"
    folder.mkdir(parents=True)
    source = folder / "source.md"
    source.write_bytes(path.read_bytes())
    return path, doc, source


def _section(key, **changes):
    return Section(id=key, intent="body", title=key, owner="ai", **changes)


def _snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize(
    "case",
    ["empty-current", "empty-saved", "identity", "unchanged", "locked-unchanged", "locked-insert", "locked-replace"],
)
def test_restore_boundary_round_trips_through_undo_and_redo(tmp_path, case):
    saved = [] if case == "empty-saved" else [_section("first"), _section("last")]
    if case in ("locked-unchanged", "locked-insert", "locked-replace"):
        saved[0].lock = "all"
    path, doc, source = _setup(tmp_path, saved)
    if case == "empty-current":
        doc.sections = []
    elif case == "empty-saved":
        doc.sections = [_section("later")]
    elif case == "identity":
        doc.sections[0].intent = "callout"
        doc.sections[0].section = "changed-outline"
    elif case == "locked-unchanged":
        doc.sections[-1].paragraphs = ["Later wording."]
    elif case == "locked-insert":
        doc.sections.pop(0)
    elif case == "locked-replace":
        doc.sections[0].lock = None
        doc.sections[0].component = "callout"
        doc.sections[0].because = "Later component choice."
    path.write_text(serialise(doc), encoding="utf-8")
    before = path.read_bytes()
    result = api.restore(str(path), "v1", base_rev=0)
    assert result.rev == 1
    assert path.read_bytes() == source.read_bytes()
    assert api.undo(path, result.rev).rev == 2
    assert path.read_bytes() == before
    assert api.redo(path, 2).rev == 3
    assert path.read_bytes() == source.read_bytes()
    entries = (tmp_path / ".ai_docs_kit" / "oplog.jsonl").read_text().splitlines()
    assert len(entries) == 3
    assert all(json.loads(line)["inverse"] is not None for line in entries)


@pytest.mark.parametrize("field", ["context", "sources", "front", "locked-reorder", "locked-delete"])
def test_restore_refuses_unpatchable_changes_without_partial_writes(tmp_path, capsys, field):
    path, doc, source = _setup(tmp_path, [_section("first"), _section("last")])
    if field == "context":
        doc.context = "Later context."
    elif field == "sources":
        doc.sources = [Source(key="S1", text="Later source.")]
    elif field == "front":
        doc.front["title"] = "Later title"
    else:
        doc.sections[0].lock = "all"
        if field == "locked-delete":
            target = doc.model_copy(deep=True)
            target.sections = [target.sections[-1]]
            source.write_text(serialise(target), encoding="utf-8")
        else:
            doc.sections.reverse()
    doc.sections[-1].paragraphs = ["Later wording that must survive refusal."]
    path.write_text(serialise(doc), encoding="utf-8")
    before = _snapshot(tmp_path)
    code = cli.main(["restore", str(path), "v1"])
    output = capsys.readouterr()
    assert code == 1
    assert not output.out and len(output.err.splitlines()) == 1
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("version", ["../v1", "", "v1\n", "/v1"])
def test_restore_rejects_non_version_paths(tmp_path, version):
    path, _, _ = _setup(tmp_path, [_section("first")])
    before = _snapshot(tmp_path)
    with pytest.raises(ValueError, match="expected a version"):
        api.restore(path, version, 0)
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("ids", [(None,), ("same", "same")])
def test_restore_refuses_ambiguous_section_ids(tmp_path, ids):
    path, _, _ = _setup(tmp_path, [_section(key) for key in ids])
    before = _snapshot(tmp_path)
    with pytest.raises(PatchRejected, match="unique section ids"):
        api.restore(path, "v1", 0)
    assert _snapshot(tmp_path) == before
