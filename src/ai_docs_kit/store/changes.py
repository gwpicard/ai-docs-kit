"""Which sections a stored version changed against an earlier one."""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ai_docs_kit.model import Format
from ai_docs_kit.render.compose import ComposedSection, Composition
from ai_docs_kit.store import Version


class VersionChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc: str
    format: Format
    from_version: int | None
    to_version: int
    edited: list[str]
    regenerated: list[str]
    added: list[str]
    removed: list[str]


def _composition(version: Version) -> list[ComposedSection]:
    text = (version.path / "composition.json").read_text(encoding="utf-8")
    return Composition.model_validate_json(text).sections


def _touched(doc_name: str, oplog: Path, low: int, high: int) -> tuple[set[str], set[str]]:
    edited: set[str] = set()
    regenerated: set[str] = set()
    if not oplog.is_file():
        return edited, regenerated
    for line in oplog.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict) or entry.get("file") != doc_name:
            continue
        rev = entry.get("rev")
        if not isinstance(rev, int) or not low < rev <= high:
            continue
        author = entry.get("author")
        if author not in ("human", "ai"):
            continue
        target = edited if author == "human" else regenerated
        for op in entry.get("ops", []):
            if isinstance(op, dict) and isinstance(op.get("section_id"), str):
                target.add(op["section_id"])
    return edited, regenerated


def version_changes(doc_path: Path, newer: Version, older: Version | None, oplog: Path) -> VersionChanges:
    new_sections = _composition(newer)
    old_sections = _composition(older) if older else []
    old_by_id = {section.id: section for section in old_sections}
    new_ids = {section.id for section in new_sections}
    edited: set[str] = set()
    regenerated: set[str] = set()
    if older and newer.manifest.doc_rev > older.manifest.doc_rev:
        edited, regenerated = _touched(doc_path.name, oplog, older.manifest.doc_rev, newer.manifest.doc_rev)
    for section in new_sections:
        before = old_by_id.get(section.id)
        if before and section.id not in edited | regenerated and before.props != section.props:
            edited.add(section.id)
    return VersionChanges(
        doc=doc_path.stem,
        format=newer.manifest.format,
        from_version=older.number if older else None,
        to_version=newer.number,
        edited=[s.id for s in new_sections if s.id in edited and s.id in old_by_id],
        regenerated=[s.id for s in new_sections if s.id in regenerated and s.id in old_by_id],
        added=[s.id for s in new_sections if s.id not in old_by_id],
        removed=[s.id for s in old_sections if s.id not in new_ids],
    )
