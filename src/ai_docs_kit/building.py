"""Shared rendering, deterministic look and immutable version build path."""

import asyncio
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

from pydantic import TypeAdapter, ValidationError

from ai_docs_kit.agents.gatherer import Fact
from ai_docs_kit.checks.catalogue import all_rules
from ai_docs_kit.facts.layout import LayoutFacts
from ai_docs_kit.loop.look import Look
from ai_docs_kit.model import Document, Finding
from ai_docs_kit.render.compose import ComposeError, Composition, assemble, compose, font_paths
from ai_docs_kit.render.marks import SectionMark
from ai_docs_kit.render.typst import TypstError, compile_pdf
from ai_docs_kit.source.files import current_rev
from ai_docs_kit.source.parser import parse
from ai_docs_kit.source.read import read_source
from ai_docs_kit.store import Version, write_version
from ai_docs_kit.store.gathered import GatheredFactsError, gathered_facts_path, read_gathered_facts
from ai_docs_kit.theme import Theme, ThemeError
from ai_docs_kit.theme.rules import load_theme_rules


class _Built(NamedTuple):
    doc: Document
    findings: list[Finding]
    render: Path
    main: Path
    pdf: Path
    comp: Composition


class _BuildFailed(ValueError):
    def __init__(self, message: str, code: int = 2) -> None:
        super().__init__(message)
        self.code = code


def _parse(file: Path, *, reader: Callable[[Path], str] = read_source) -> tuple[Document, list[Finding]]:
    try:
        text = reader(file)
    except UnicodeDecodeError as error:
        raise _BuildFailed(f"{file}: not valid UTF-8 ({error.reason} at byte {error.start})") from error
    doc, findings = parse(text)
    errors = [f for f in findings if f.severity == "error"]
    if errors:
        raise _BuildFailed("\n".join(_line(f) for f in errors))
    doc.rev = current_rev(file.parent / ".ai_docs_kit" / "oplog.jsonl")
    return doc, findings


def _draw(file: Path, out: Path, doc: Document, findings: list[Finding], comp: Composition, theme: Theme) -> _Built:
    render = out / "render"
    if render.exists():
        shutil.rmtree(render)
    main = assemble(comp, render, theme=theme)
    pdf = out / f"{file.stem}.pdf"
    try:
        compile_pdf(main, render, pdf, font_paths(render))
    except TypstError as error:
        raise _BuildFailed(str(error)) from error
    return _Built(doc, findings, render, main, pdf, comp)


def _render(file: Path, out: Path, theme: Theme) -> _Built:
    doc, findings = _parse(file)
    try:
        comp = compose(doc, assets=[file.parent / "assets", theme.root / "assets"])
    except ComposeError as error:
        raise _BuildFailed(str(error)) from error
    return _draw(file, out, doc, findings, comp, theme)


def _line(finding: Finding) -> str:
    return f"{finding.severity} {finding.rule_id} {finding.section_id or '-'} {finding.message}"


def _sheet(built: _Built, result: Any, out: Path) -> Path:
    """Draw the contact sheet for slides, or the facing-page spreads for a document."""
    from ai_docs_kit.facts.sheets import contact_sheet, page_labels, spread_sheet
    from ai_docs_kit.store import page_index

    if built.comp.format != "slides":
        return spread_sheet(result.pngs, page_labels(result.facts), out / "spreads.png")
    components = {s.id: s.component for s in built.comp.sections}
    labels = [
        " ".join([str(page["page"]), *(components[s] for s in page["sections"] if s in components)])
        for page in page_index(result.facts, [])
    ]
    return contact_sheet(result.pngs, labels, out / "contact.png")


def _pptx(file: Path, out: Path, built: _Built, facts: Any) -> Path | None:
    """Write the PowerPoint copy beside the PDF; a document has none."""
    if built.comp.format != "slides":
        return None
    from ai_docs_kit.render.pptx_copy import PptxError, write_pptx

    try:
        return write_pptx(
            out / f"{file.stem}.pptx",
            facts=facts,
            comp=built.comp,
            doc=built.doc,
            main=built.main,
            render=built.render,
            font_paths=font_paths(built.render),
        )
    except TypstError as error:
        raise _BuildFailed(str(error)) from error
    except PptxError as error:
        raise _BuildFailed(str(error), code=1) from error


def _docx(file: Path, out: Path, built: _Built, theme: Theme) -> Path | None:
    """Write the Word copy beside the PDF; slides have none."""
    if built.comp.format != "doc":
        return None
    from ai_docs_kit.render.word import write_docx

    return write_docx(out / f"{file.stem}.docx", comp=built.comp, theme=theme)


def _source_facts(file: Path, doc: Document) -> list[Fact] | None:
    facts_path = file.parent / ".ai_docs_kit" / "write" / file.stem / "facts.json"
    gathered_path = gathered_facts_path(file)
    if not facts_path.exists() and not gathered_path.exists():
        # Human wording bypasses the edit guard, so it must be checked even
        # before facts have been gathered. Retain the legacy AI-only fallback.
        return [] if any(section.owner == "human" for section in doc.sections) else None
    try:
        facts = TypeAdapter(list[Fact]).validate_json(facts_path.read_bytes()) if facts_path.exists() else []
    except ValidationError as error:
        raise _BuildFailed(f"{facts_path}: not valid facts ({error.error_count()} errors)") from error
    try:
        facts.extend(
            Fact(text=fact.text, source_key=fact.source, locator=fact.locator)
            for fact in read_gathered_facts(gathered_path, missing_ok=True)
        )
    except GatheredFactsError as error:
        raise _BuildFailed(str(error)) from error
    return facts


def inspect_render(
    file: Path, out: Path, theme: Theme, built: _Built, *, final: bool = False, project: Path | None = None
) -> Look:
    """Run the normal deterministic look, optionally keeping its cache in scratch."""
    from ai_docs_kit.loop.look import LookContext, look

    try:
        rules = all_rules() + load_theme_rules(theme)
    except ThemeError as error:
        raise _BuildFailed(str(error)) from error
    result = asyncio.run(
        look(
            built.pdf,
            built.comp,
            LookContext(
                doc=built.doc,
                theme=theme,
                main=built.main,
                project=file.parent if project is None else project,
                workdir=out / "look",
                rules=rules,
                critic=None,
                final=final,
                assets=[file.parent / "assets", theme.root / "assets"],
                source_facts=_source_facts(file, built.doc),
            ),
        )
    )
    return result


def _located_findings(findings: list[Finding], facts: LayoutFacts) -> list[Finding]:
    """Locate source findings at their section's start without changing source-only checks."""
    pages = {mark.id: mark.page for mark in facts.marks if isinstance(mark, SectionMark) and mark.edge == "start"}
    return [
        finding.model_copy(update={"page": pages[owner]})
        if finding.tier == "source" and finding.page is None and (owner := finding.owner or finding.section_id) in pages
        else finding
        for finding in findings
    ]


def build_document(
    file: Path,
    out: Path,
    theme: Theme,
    *,
    final: bool = False,
    on_rendered: Callable[[Path], None] | None = None,
    pptx_writer: Callable[[Path, Path, _Built, Any], Path | None] = _pptx,
) -> tuple[Version, list[Finding]]:
    """Render, look and save a version for both the CLI and Python API."""
    for directory in (out / "render", out / "look"):
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise _BuildFailed(f"ai_docs_kit: cannot use {directory} as a build folder: {error.strerror}") from error
    built = _render(file, out, theme)
    if on_rendered is not None:
        on_rendered(built.pdf)
    result = inspect_render(file, out, theme, built, final=final)
    sheet = _sheet(built, result, out)
    pptx = pptx_writer(file, out, built, result.facts)
    docx = _docx(file, out, built, theme)
    findings = _located_findings(built.findings + result.findings, result.facts)
    try:
        version = write_version(
            file,
            built.doc,
            built.comp,
            built.pdf,
            result.facts,
            findings,
            result.pngs,
            None,
            theme=theme,
            final=final,
            look=result.record(),
            sheet=sheet,
            pptx=pptx,
            docx=docx,
        )
    except OSError as error:
        raise _BuildFailed(f"Cannot write version: {error}") from error
    (out / f"{file.stem}.findings.json").write_bytes(TypeAdapter(list[Finding]).dump_json(findings, indent=2))
    return version, findings
