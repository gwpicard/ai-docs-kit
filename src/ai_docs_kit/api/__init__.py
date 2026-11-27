"""Typed, deterministic access to documents, builds and scratch previews.

Paths accept strings or pathlib Paths. Functions raise OSError for filesystem
failures, ValueError for invalid documents or saved data, and ThemeError for an
invalid theme selection. Build failures carry the CLI's diagnostic and code.
Edit refusals raise PatchRejected with a code and message.
Nothing is printed and no model service is called.
"""

import json
import re
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from ai_docs_kit.api.models import (
    BuildResult,
    EditError,
    EditResult,
    FieldBox,
    FieldPage,
    Page,
    PageRegion,
    PreviewResult,
)
from ai_docs_kit.building import _render, build_document, inspect_render
from ai_docs_kit.facts.layout import LayoutFacts
from ai_docs_kit.model import Document, Finding, Patch, PatchOp, Section
from ai_docs_kit.render.compose import Composition
from ai_docs_kit.source.files import UNPARSEABLE_RULES, apply_to_document, current_rev, project_lock
from ai_docs_kit.source.ids import IdStore
from ai_docs_kit.source.parser import parse
from ai_docs_kit.source.patches import PatchRejected
from ai_docs_kit.source.read import read_source
from ai_docs_kit.store import Version, field_index, load_version, page_index
from ai_docs_kit.theme import load_theme, resolve_theme

__all__ = [
    "BuildResult",
    "Document",
    "EditError",
    "EditResult",
    "FieldBox",
    "FieldPage",
    "Finding",
    "Page",
    "PageRegion",
    "PatchRejected",
    "PreviewResult",
    "Version",
    "add_section",
    "build",
    "delete_section",
    "edit_fields",
    "export_api_schemas",
    "list_findings",
    "list_versions",
    "move_section",
    "preview",
    "read_document",
]


def read_document(path: Path | str) -> Document:
    """Read every working-file field and the current project oplog revision.

    Reading neither stamps ids nor creates project state. As with section list,
    source-check findings do not hide otherwise readable document content.
    """
    path = Path(path)
    doc, findings = parse(read_source(path))
    broken = sorted({finding.rule_id for finding in findings if finding.rule_id in UNPARSEABLE_RULES})
    if broken:
        raise ValueError(f"{path}: cannot be read safely: {', '.join(broken)}")
    doc.rev = current_rev(path.parent / ".ai_docs_kit" / "oplog.jsonl")
    return doc


def _section(doc: Document, section_id: str) -> Section:
    for section in doc.sections:
        if section.id == section_id:
            return section
    raise PatchRejected("unknown-section", f"no section with id {section_id!r}")


def _edit(path: Path | str, op: PatchOp, base_rev: int) -> EditResult:
    path = Path(path)
    store = path.parent / ".ai_docs_kit"
    with project_lock(store):
        before = read_document(path)
        if before.rev != base_rev:
            raise PatchRejected("stale-base-rev", f"document is at rev {before.rev}, not {base_rev}; read it again")
        old = None if op.op == "insert_after" else _section(before, op.section_id)
        if old is not None and old.lock == "all":
            raise PatchRejected("lock-all", f"section {old.id} is locked")
        patch = Patch(base_rev=base_rev, author="human", reason=f"human {op.op}", ops=[op])
        result = apply_to_document(path, before, patch, store / "oplog.jsonl", IdStore(store / "ids.json"))
        if op.op == "insert_after":
            position = next((i + 1 for i, section in enumerate(result.sections) if section.id == op.after_id), 0)
            changed = result.sections[position]
        elif op.op == "delete_section":
            assert old is not None
            changed = old
        else:
            changed = _section(result, op.section_id)
        return EditResult(rev=result.rev, section=changed)


def edit_fields(path: Path | str, section_id: str, fields: dict[str, Any], base_rev: int) -> EditResult:
    """Keep a person's fields, mark human ownership and bypass the fact guard."""
    return _edit(path, PatchOp(op="set_fields", section_id=section_id, fields={**fields, "owner": "human"}), base_rev)


def add_section(path: Path | str, after_id: str | None, section: Section, base_rev: int) -> EditResult:
    """Insert a person's section, allocating an id when absent; None prepends."""
    return _edit(
        path,
        PatchOp(
            op="insert_after",
            section_id=section.id or "__new",
            after_id=after_id,
            value=section.model_copy(deep=True, update={"owner": "human"}),
        ),
        base_rev,
    )


def delete_section(path: Path | str, section_id: str, base_rev: int) -> EditResult:
    """Delete a section and return its removed content with the new revision."""
    return _edit(path, PatchOp(op="delete_section", section_id=section_id), base_rev)


def move_section(path: Path | str, section_id: str, after_id: str, base_rev: int) -> EditResult:
    """Move a section after another section without changing its content or id."""
    return _edit(path, PatchOp(op="move_section", section_id=section_id, after_id=after_id), base_rev)


def build(path: Path | str, theme: Path | str | None = None) -> BuildResult:
    """Build the PDF and editable copy, run checks and save the next version."""
    path = Path(path)
    selected = load_theme(Path(theme) if theme is not None else resolve_theme(path).path)
    version, findings = build_document(path, path.parent / "build", selected)
    return BuildResult.from_version(version, findings)


def preview(path: Path | str, scratch: Path | str, theme: Path | str | None = None) -> PreviewResult:
    """Render and check the whole document in scratch without writing a version.

    Layout facts are cached by PDF content and composition in scratch, using
    the normal look cache. Checks run each time to reflect changed theme rules.
    Scratch must not contain the working file or lie in its state or versions.
    """
    path, scratch = Path(path), Path(scratch)
    resolved, destination = path.resolve(), scratch.resolve()
    # Builds and the oplog use the supplied working-file path, even when that
    # file is a symlink. Resolve those stores as well as the scratch folder.
    protected = (path.with_suffix(".versions").resolve(), (path.parent / ".ai_docs_kit").resolve())
    if resolved.is_relative_to(destination) or any(
        destination.is_relative_to(folder) or folder.is_relative_to(destination) for folder in protected
    ):
        raise ValueError("scratch must be separate from the working file, oplog and versions")
    selected = load_theme(Path(theme) if theme is not None else resolve_theme(path).path)
    scratch.mkdir(parents=True, exist_ok=True)
    built = _render(path, scratch, selected)
    result = inspect_render(path, scratch, selected, built, project=scratch)
    findings = built.findings + result.findings
    return PreviewResult(
        pngs=result.pngs,
        pages=TypeAdapter(list[Page]).validate_python(page_index(result.facts, findings)),
        fields=TypeAdapter(list[FieldPage]).validate_python(field_index(result.facts, built.comp)),
        findings=findings,
    )


def list_findings(version: Path | str) -> list[Finding]:
    """Read engine findings from a saved version without consulting its source."""
    return TypeAdapter(list[Finding]).validate_json((Path(version) / "findings.json").read_bytes())


def list_versions(path: Path | str) -> list[Version]:
    """List saved versions in ascending numeric order; a missing store is empty."""
    root = Path(path).with_suffix(".versions")
    if not root.exists():
        return []
    numbered = [
        (int(match.group(1)), folder)
        for folder in root.iterdir()
        if folder.is_dir() and (match := re.fullmatch(r"v(\d+)", folder.name))
    ]
    return [load_version(folder) for _, folder in sorted(numbered)]


def _version_preview(version: Path) -> PreviewResult:
    """Read the same preview model from an immutable version for look --pages."""
    index = version / "pages" / "pages.json"
    try:
        pages = TypeAdapter(list[Page]).validate_python(json.loads(index.read_bytes())["pages"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"{index}: malformed page index") from error
    facts = LayoutFacts.model_validate_json((version / "layout.json").read_bytes())
    composition = Composition.model_validate_json((version / "composition.json").read_bytes())
    return PreviewResult(
        pngs=[version / "pages" / page.image for page in pages],
        pages=pages,
        fields=TypeAdapter(list[FieldPage]).validate_python(field_index(facts, composition)),
        findings=list_findings(version),
    )


def export_api_schemas(directory: Path) -> list[Path]:
    """Regenerate the schema pins for every public function's result model."""
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for model in (Document, BuildResult, PreviewResult, EditResult, EditError, Finding, Version):
        path = directory / f"{model.__name__}.schema.json"
        path.write_text(
            json.dumps(model.model_json_schema(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        paths.append(path)
    return paths
