"""History replay keeps deletion inverses usable, including a prepended section."""

import json
from pathlib import Path

import pytest

from ai_docs_kit import api
from ai_docs_kit.model import Document, Section
from ai_docs_kit.source.serialiser import serialise


@pytest.mark.parametrize("section_id", ["first", "middle", "last"])
def test_delete_history_records_an_inverse_for_every_step(tmp_path, section_id):
    path = tmp_path / "note.md"
    document = Document(
        front={"format": "doc"},
        format="doc",
        sections=[Section(id=key, intent="body", paragraphs=[key]) for key in ("first", "middle", "last")],
    )
    path.write_text(serialise(document), encoding="utf-8")
    original = path.read_bytes()
    api.delete_section(path, section_id, 0)
    deleted = path.read_bytes()
    assert deleted != original
    for command, expected in ((api.undo, original), (api.redo, deleted), (api.undo, original)):
        revision = api.read_document(path).rev
        result = command(path, revision)
        assert result.target_rev == 1
        assert path.read_bytes() == expected
        entries = [json.loads(line) for line in (tmp_path / ".ai_docs_kit/oplog.jsonl").read_text().splitlines()]
        assert entries[-1]["inverse"] is not None, "history steps must themselves record an inverse"
    exported = tmp_path / "schemas"
    api.export_api_schemas(exported)
    name = "HistoryResult.schema.json"
    pin = Path(__file__).resolve().parents[1] / "docs/schemas/api" / name
    assert json.loads(pin.read_text()) == api.HistoryResult.model_json_schema()
    assert (exported / name).read_bytes() == pin.read_bytes()
