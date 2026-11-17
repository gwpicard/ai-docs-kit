import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from pydantic import TypeAdapter, ValidationError

from ai_docs_kit import __version__
from ai_docs_kit.agents.gatherer import Fact
from ai_docs_kit.brand.cli import add_brand_commands, run_brand
from ai_docs_kit.checks.catalogue import all_rules, document_rules
from ai_docs_kit.checks.engine import CheckContext, run_checks
from ai_docs_kit.config import default_config_text
from ai_docs_kit.facts.layout import layout_facts
from ai_docs_kit.facts.raster import PdfiumRasteriser
from ai_docs_kit.model import Document, Finding
from ai_docs_kit.render.compose import ComposeError, Composition, assemble, compose, font_paths
from ai_docs_kit.render.kit import read_tokens
from ai_docs_kit.render.typst import INSTALL_COMMAND, TYPST_VERSION, TypstError, compile_pdf, typst_version
from ai_docs_kit.section_command import add_section_commands, run_section
from ai_docs_kit.source.parser import parse
from ai_docs_kit.theme import Theme, ThemeError, load_theme, neutral_theme
from ai_docs_kit.theme.rules import load_theme_rules

if TYPE_CHECKING:
    from ai_docs_kit.store import LookFinding

MIN_PYTHON = (3, 12)


def _python_line() -> tuple[str, bool]:
    v = sys.version_info
    version = f"{v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) < MIN_PYTHON:
        return f"python: {version} (needs {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or later)", False
    return f"python: {version}", True


def _typst_lines() -> list[str]:
    executable = shutil.which("typst")
    if executable is None:
        return ["typst: missing", f"install: {INSTALL_COMMAND}"]
    found = typst_version(executable)
    if found != TYPST_VERSION:
        return [f"typst: {found}", f"needs: typst {TYPST_VERSION}"]
    return [f"typst: {found}"]


def _doctor() -> int:
    python_line, python_ok = _python_line()
    print(python_line)
    for line in _typst_lines():
        print(line)
    print(f"anthropic key: {'set' if os.environ.get('ANTHROPIC_API_KEY') else 'missing'}")
    return 0 if python_ok else 1


def _init(directory: Path) -> int:
    path = directory / "ai_docs_kit.toml"
    directory.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as file:
            file.write(default_config_text())
    except FileExistsError:
        print(f"{path} already exists", file=sys.stderr)
        return 1
    (directory / "sources").mkdir(exist_ok=True)
    print(path)
    return 0


class _Built(NamedTuple):
    doc: Document
    findings: list[Finding]
    render: Path
    main: Path
    pdf: Path
    comp: Composition


class _BuildFailed(Exception):
    pass


def _out_dir(file: Path, out: Path | None) -> Path:
    return out if out is not None else file.parent / "build"


def _parse(file: Path) -> tuple[Document, list[Finding]]:
    try:
        text = file.read_text()
    except UnicodeDecodeError as error:
        raise _BuildFailed(f"{file}: not valid UTF-8 ({error.reason} at byte {error.start})") from error
    doc, findings = parse(text)
    errors = [f for f in findings if f.severity == "error"]
    if errors:
        raise _BuildFailed("\n".join(_line(f) for f in errors))
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


def _build(file: Path, out: Path, theme: Theme, *, final: bool = False) -> int:
    built = _render(file, out, theme)
    print(built.pdf)
    return _version_build(file, out, theme, built, final)


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


def _pptx(file: Path, out: Path, built: _Built, facts: Any, theme: Theme) -> Path | None:
    """Write the PowerPoint copy beside the PDF; a document has none."""
    if built.comp.format != "slides":
        return None
    from ai_docs_kit.render.pptx_copy import write_pptx

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


def _docx(file: Path, out: Path, built: _Built, theme: Theme) -> Path | None:
    """Write the Word copy beside the PDF; slides have none."""
    if built.comp.format != "doc":
        return None
    from ai_docs_kit.render.word import write_docx

    return write_docx(out / f"{file.stem}.docx", comp=built.comp, theme=theme)


def _version_build(file: Path, out: Path, theme: Theme, built: _Built, final: bool) -> int:
    from ai_docs_kit.loop.look import LookContext, look
    from ai_docs_kit.store import write_version
    from ai_docs_kit.store.gate import ship_gate

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
                project=file.parent,
                workdir=out / "look",
                rules=rules,
                critic=None,
                final=final,
                assets=[file.parent / "assets", theme.root / "assets"],
            ),
        )
    )
    sheet = _sheet(built, result, out)
    pptx = _pptx(file, out, built, result.facts, theme)
    docx = _docx(file, out, built, theme)
    version = write_version(
        file,
        built.doc,
        built.comp,
        built.pdf,
        result.facts,
        built.findings + result.findings,
        result.pngs,
        None,
        theme=theme,
        final=final,
        look=result.record(),
        sheet=sheet,
        pptx=pptx,
        docx=docx,
    )
    print(version.path)
    return _gate_report(ship_gate(version)) if final else 0


def _gate_report(reasons: list[str]) -> int:
    for reason in reasons:
        print(f"not ready: {reason}")
    if not reasons:
        print("gate: passed")
    return int(bool(reasons))


def _ready(args: argparse.Namespace) -> int:
    from ai_docs_kit.store import load_version
    from ai_docs_kit.store.gate import mark_ready

    try:
        version = load_version(args.version_dir)
        reasons = mark_ready(version, force=args.force, reason=args.reason)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 2
    if reasons and not args.force:
        for reason in reasons:
            print(f"not ready: {reason}")
        return 1
    print(f"ready (forced: {args.reason})" if args.force else "ready")
    return 0


def _read_pages(version_dir: Path) -> list[dict[str, Any]]:
    pages_path = version_dir / "pages" / "pages.json"
    try:
        pages = json.loads(pages_path.read_text(encoding="utf-8"))["pages"]
        if not isinstance(pages, list):
            raise TypeError("pages is not a list")
        for page in pages:
            page["page"], ", ".join(page["sections"])
    except OSError as error:
        raise ValueError(f"{pages_path}: cannot read page index ({error.strerror or error})") from error
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"{pages_path}: malformed page index ({error!r})") from error
    return pages


def _look_pages(version_dir: Path) -> int:
    findings_path = version_dir / "findings.json"
    pages = _read_pages(version_dir)
    lines = [f"page {page['page']}: {', '.join(page['sections'])}" for page in pages]
    try:
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        notes = [
            f"- {f['rule_id']} {f['severity']} page {f.get('page')} section {f.get('section_id')}: {f['message']}"
            for f in findings
        ]
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError(f"{findings_path}: malformed findings ({error!r})") from error
    print("\n".join([*lines, "engine findings (do not repeat):", *notes]))
    return 0


def _same_finding(a: "LookFinding", b: "LookFinding") -> bool:
    return (a.page, a.section, a.severity, a.message) == (b.page, b.section, b.severity, b.message)


def _look_findings(version_dir: Path, file: Path) -> int:
    from pydantic import ValidationError

    from ai_docs_kit.store import LookFinding, load_version, update_manifest

    version = load_version(version_dir)
    pages = _read_pages(version_dir)
    raw = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        print(f"{file}: expected a JSON array of findings", file=sys.stderr)
        return 2
    problems: list[str] = []
    accepted: list[LookFinding] = []
    for i, item in enumerate(raw, 1):
        try:
            finding = LookFinding.model_validate(item)
        except ValidationError as error:
            problems.extend(
                f"finding {i}: {'.'.join(map(str, e['loc']))}: {e['msg']} ({e['input']!r})" for e in error.errors()
            )
            continue
        blank = [name for name in ("rule", "message") if not getattr(finding, name).strip()]
        if blank:
            problems.append(f"finding {i}: {' and '.join(blank)} must not be blank")
        elif not 1 <= finding.page <= len(pages):
            problems.append(f"finding {i}: page {finding.page} is out of range 1-{len(pages)}")
        elif finding.section not in pages[finding.page - 1]["sections"]:
            problems.append(f"finding {i}: section {finding.section} is not on page {finding.page}")
        else:
            accepted.append(finding)
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 2
    record = version.manifest.look
    if record is None:
        print(f"{version_dir}: no look record; the engine's look has not run", file=sys.stderr)
        return 2
    merged = list(record.agent or [])
    added = 0
    for finding in accepted:
        if not any(_same_finding(finding, known) for known in merged):
            merged.append(finding)
            added += 1
    if added or record.agent is None:
        update_manifest(version_dir, look=record.model_copy(update={"agent": merged}))
    print(f"recorded {added} findings")
    return 0


def _look(args: argparse.Namespace) -> int:
    if args.pages == (args.findings is not None):
        print("give exactly one of --pages or --findings", file=sys.stderr)
        return 2
    try:
        if args.pages:
            return _look_pages(args.version_dir)
        return _look_findings(args.version_dir, args.findings)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 2


def _sent(args: argparse.Namespace) -> int:
    from ai_docs_kit.store import load_version
    from ai_docs_kit.store.gate import mark_sent

    if args.latest is not None:
        root = args.latest.parent / f"{args.latest.stem}.versions"
        sent = [
            (v.number, d) for d in root.glob("v*") if (v := _try_load(d)) is not None and v.manifest.state == "sent"
        ]
        if sent:
            print(max(sent)[1])
        return 0
    if args.version_dir is None or args.to is None:
        print("sent needs a version folder and --to, or --latest", file=sys.stderr)
        return 2
    try:
        reasons = mark_sent(load_version(args.version_dir), args.to, force=args.force, reason=args.reason)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 2
    if reasons and not args.force:
        for reason in reasons:
            print(f"not sent: {reason}")
        return 1
    print(f"sent to {args.to} (forced: {args.reason})" if reasons else f"sent to {args.to}")
    return 0


def _try_load(directory: Path) -> Any:
    from ai_docs_kit.store import load_version

    try:
        return load_version(directory)
    except (OSError, ValueError):
        return None


def _check(file: Path, out: Path, theme: Theme, *, final: bool = False, outline: bool = False) -> int:
    doc, parsed = _parse(file)
    try:
        rules = all_rules() + load_theme_rules(theme)
        if outline:
            rules += document_rules()
    except ThemeError as error:
        raise _BuildFailed(str(error)) from error
    assets = [file.parent / "assets", theme.root / "assets"]
    facts_path = file.parent / ".ai_docs_kit" / "write" / file.stem / "facts.json"
    source_facts = None
    if facts_path.exists():
        try:
            source_facts = TypeAdapter(list[Fact]).validate_json(facts_path.read_bytes())
        except ValidationError as error:
            raise _BuildFailed(f"{facts_path}: not valid facts ({error.error_count()} errors)") from error
    try:
        comp = compose(doc, assets=assets)
    except ComposeError:
        # Without layout facts the engine runs only the source tier.
        return _report(
            file,
            out,
            parsed
            + run_checks(rules, CheckContext(doc, theme=theme, final=final, assets=assets, source_facts=source_facts)),
        )
    built = _draw(file, out, doc, parsed, comp, theme)
    facts = layout_facts(built.pdf, built.main, built.render, font_paths=font_paths(built.render))
    pages_png = PdfiumRasteriser().render(built.pdf, out / "pages")
    ctx = CheckContext(
        built.doc,
        facts,
        read_tokens(built.render),
        theme=theme,
        composition=comp,
        final=final,
        assets=assets,
        pages_png=pages_png,
        source_facts=source_facts,
    )
    return _report(file, out, built.findings + run_checks(rules, ctx))


def _report(file: Path, out: Path, findings: list[Finding]) -> int:
    report = TypeAdapter(list[Finding]).dump_json(findings, indent=2)
    (out / f"{file.stem}.findings.json").write_bytes(report)
    for finding in findings:
        print(_line(finding))
    if not findings:
        print("no findings")
    return 1 if any(f.severity == "error" for f in findings) else 0


def _add_file_command(subparsers: Any, name: str, help: str) -> None:
    command = subparsers.add_parser(name, help=help)
    command.add_argument("file", type=Path, help="the working file")
    command.add_argument("--out", type=Path, default=None, help="output folder (default: build beside the file)")
    command.add_argument("--theme", type=Path, default=None, help="theme folder (default: the neutral theme)")
    if name in ("build", "check"):
        command.add_argument("--final", action="store_true", help="treat the working file as a final build")
    if name == "check":
        command.add_argument("--outline", action="store_true", help="check conformance to the doctype outline")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-docs-kit")
    parser.add_argument("--version", action="version", version=f"ai_docs_kit {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_brand_commands(subparsers)
    add_section_commands(subparsers)
    subparsers.add_parser("doctor", help="report what is installed and what is missing")
    init = subparsers.add_parser("init", help="initialise a project")
    init.add_argument("directory", type=Path, help="project folder")
    _add_file_command(subparsers, "build", "render a working file to PDF")
    _add_file_command(subparsers, "check", "render a working file and report what the M1 rules find")
    _add_file_command(subparsers, "write", "prepare and draft a working file")
    ready = subparsers.add_parser("ready", help="mark a version ready")
    ready.add_argument("version_dir", type=Path)
    ready.add_argument("--force", action="store_true")
    ready.add_argument("--reason")
    look = subparsers.add_parser("look", help="print the pages for the look agent or record its findings")
    look.add_argument("version_dir", type=Path)
    look.add_argument("--pages", action="store_true")
    look.add_argument("--findings", type=Path)
    sent = subparsers.add_parser("sent", help="record that a version was sent")
    sent.add_argument("version_dir", type=Path, nargs="?")
    sent.add_argument("--to")
    sent.add_argument("--latest", type=Path)
    sent.add_argument("--force", action="store_true")
    sent.add_argument("--reason")
    write = subparsers.choices["write"]
    write.add_argument("--approve", action="store_true")
    write.add_argument("--yes", action="store_true")
    theme = subparsers.add_parser("theme", help="work with themes")
    theme_commands = theme.add_subparsers(dest="theme_command", required=True)
    test = theme_commands.add_parser("test", help="test a theme")
    test.add_argument("--theme", type=Path, default=None, help="theme folder")
    evaluation = subparsers.add_parser("eval", help="run evaluations")
    eval_commands = evaluation.add_subparsers(dest="eval_command", required=True)
    heal = eval_commands.add_parser("heal", help="run the heal evaluation")
    heal.add_argument("--live", action="store_true")
    heal.add_argument("--cases", type=Path, default=Path("tests/fixtures/heal-eval"))
    heal.add_argument("--out", type=Path, default=Path("evals/RESULTS.md"))
    heal.add_argument("--theme", type=Path, default=None)
    critic = eval_commands.add_parser("critic", help="run the critic evaluation")
    critic.add_argument("--live", action="store_true")
    critic.add_argument("--cases", type=Path, default=Path("tests/fixtures/critic-eval"))
    critic.add_argument("--out", type=Path, default=Path("evals/CRITIC.md"))
    critic.add_argument("--calibration", type=Path, default=None)
    critic.add_argument("--theme", type=Path, default=None)
    return parser


FILE_COMMANDS = {"build": _build, "check": _check}


def _theme(folder: Path | None) -> Theme:
    try:
        return neutral_theme() if folder is None else load_theme(folder)
    except ThemeError as error:
        raise _BuildFailed(str(error)) from error


def _run_file_command(args: argparse.Namespace) -> int:
    out = _out_dir(args.file, args.out)
    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        print(f"ai_docs_kit: cannot use {out} as the output folder: {error.strerror}", file=sys.stderr)
        return 2
    try:
        if args.command == "check":
            return _check(args.file, out, _theme(args.theme), final=args.final, outline=args.outline)
        return _build(args.file, out, _theme(args.theme), final=args.final)
    except _BuildFailed as error:
        print(error, file=sys.stderr)
        return 2


def main(argv: list[str] | None = None) -> int:
    try:
        args = _build_parser().parse_args(argv)
    except SystemExit as error:
        if error.code == 2 and (argv if argv is not None else sys.argv[1:])[:2] == ["brand", "init"]:
            return 2
        raise
    if args.command == "brand":
        return run_brand(args)
    if args.command == "section":
        return run_section(args)
    if args.command == "doctor":
        return _doctor()
    if args.command == "init":
        return _init(args.directory)
    if args.command == "ready":
        return _ready(args)
    if args.command == "look":
        return _look(args)
    if args.command == "sent":
        return _sent(args)
    if args.command in ("write", *FILE_COMMANDS) and not args.file.is_file():
        print(f"{args.file}: no such working file", file=sys.stderr)
        return 2
    if args.command == "write":
        return _write(args)
    if args.command in FILE_COMMANDS:
        return _run_file_command(args)
    if args.command == "theme":
        return _run_theme_test(args.theme)
    if args.command == "eval":
        return _heal(args) if args.eval_command == "heal" else _critic_eval(args)
    return 1


def _critic_eval(args: argparse.Namespace) -> int:
    if args.live and os.environ.get("DOCLA_LIVE") != "1":
        print("Live evaluation requires DOCLA_LIVE=1", file=sys.stderr)
        return 2
    from ai_docs_kit.evals.critic import ScriptedCritic, calibration_yaml, load_cases, render_results, run_critic

    cases = load_cases(args.cases)
    theme = _theme(args.theme)
    verdict = _live_critic(args.out, theme) if args.live else ScriptedCritic()
    report = asyncio.run(run_critic(cases, verdict))
    report.mode = "live" if args.live else "offline"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_results(report))
    calibration = args.calibration or (theme.root / "rubric/calibration.yaml" if args.live else None)
    if calibration is not None:
        calibration.parent.mkdir(parents=True, exist_ok=True)
        calibration.write_text(calibration_yaml(report))
    return 0


def _live_critic(out: Path, theme: Theme) -> Any:
    from PIL import Image

    from ai_docs_kit.agents.critic import CriticImage, Region, critique
    from ai_docs_kit.agents.ledger import Ledger
    from ai_docs_kit.agents.scheduler import Scheduler
    from ai_docs_kit.config import load_project_config
    from ai_docs_kit.model import Box
    from ai_docs_kit.theme.rubric import load_rubric
    from ai_docs_kit.write import ScheduledClaude, live_transport, role_models

    config = load_project_config(Path.cwd())
    ledger = Ledger(out.parent / "critic-ledger.jsonl", config.prices, config.budget.max_usd_per_document)
    claude = ScheduledClaude(
        live_transport(), ledger, role_models(config), scheduler=Scheduler(config.loop.max_parallel_sections)
    )
    rubric = load_rubric(theme)

    async def verdict(case: Any, run: int) -> str:
        with Image.open(case.crop) as image:
            width, height = image.size
        item = rubric.get(case.rubric_id)
        findings = await critique(
            claude,
            [CriticImage(case.crop, 1, width, height, "crop")],
            [item],
            [],
            [Region("crop", None, 1, Box(x=0, y=0, w=width, h=height))],
            format=(item.applies.formats or ["slides"])[0],
        )
        return "fail" if any(f.rule_id == case.rubric_id for f in findings) else "pass"

    return verdict


def _heal(args: argparse.Namespace) -> int:
    if args.live and os.environ.get("DOCLA_LIVE") != "1":
        print("Live evaluation requires DOCLA_LIVE=1", file=sys.stderr)
        return 2
    from ai_docs_kit.evals.heal import HealCase, ScriptedWriter, load_cases, render_results, run_heal
    from ai_docs_kit.loop.micro import SectionWriter

    cases = load_cases(args.cases)
    theme = _theme(args.theme)

    def spent() -> float:
        return 0.0

    writer_for: Callable[[HealCase], SectionWriter] = ScriptedWriter
    if args.live:
        from ai_docs_kit.agents.ledger import Ledger
        from ai_docs_kit.agents.scheduler import Scheduler
        from ai_docs_kit.config import load_project_config
        from ai_docs_kit.write import ClaudeWriter, ScheduledClaude, live_transport, role_models

        config = load_project_config(Path.cwd())
        ledger = Ledger(args.out.parent / "heal-ledger.jsonl", config.prices, config.budget.max_usd_per_document)
        claude = ScheduledClaude(
            live_transport(), ledger, role_models(config), scheduler=Scheduler(config.loop.max_parallel_sections)
        )

        class LiveWriter(ClaudeWriter):
            def __init__(self, case: Any) -> None:
                super().__init__(claude, [], theme, case.document)
                self.case = case

            async def draft(self, job: Any) -> Any:
                return self.case.document.sections[0]

        writer_for = LiveWriter

        def spent() -> float:
            return ledger.total

    with tempfile.TemporaryDirectory() as directory:
        report = asyncio.run(run_heal(cases, writer_for=writer_for, theme=theme, workdir=Path(directory), spent=spent))
    report.mode = "live" if args.live else "offline"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_results(report))
    return 0 if report.gate else 1


def _write(args: argparse.Namespace) -> int:
    from ai_docs_kit.agents.cassette import CassetteMiss
    from ai_docs_kit.agents.client import AgentInvalid, AgentRefused, AgentTruncated
    from ai_docs_kit.agents.ledger import Ledger
    from ai_docs_kit.agents.scheduler import Scheduler
    from ai_docs_kit.config import ConfigError, load_project_config
    from ai_docs_kit.write import ScheduledClaude, claude_agents, role_models, run_write, transport_for

    project = args.file.parent
    try:
        config = load_project_config(project)
    except ConfigError as error:
        print(f"{project / 'ai_docs_kit.toml'}: {error}", file=sys.stderr)
        return 2
    ledger = Ledger(
        project / ".ai_docs_kit" / "write" / args.file.stem / "ledger.jsonl",
        config.prices,
        config.budget.max_usd_per_document,
    )
    try:
        theme = _theme(args.theme)
        claude = ScheduledClaude(
            transport_for(project), ledger, role_models(config), scheduler=Scheduler(config.loop.max_parallel_sections)
        )
        return asyncio.run(
            run_write(
                args.file,
                agents=claude_agents(claude, theme, config=config),
                theme=theme,
                out=_out_dir(args.file, args.out),
                approve=args.approve,
                yes=args.yes,
                spent=lambda: ledger.total,
            )
        )
    except CassetteMiss as error:
        print(
            f"{project / '.ai_docs_kit' / 'cassette.json'}: {error}; set DOCLA_LIVE=1 for live calls", file=sys.stderr
        )
    except (AgentRefused, AgentTruncated, AgentInvalid, _BuildFailed) as error:
        print(error, file=sys.stderr)
    return 2


def _run_theme_test(folder: Path | None) -> int:
    from ai_docs_kit.theme.suite import theme_test

    try:
        theme = _theme(folder)
    except _BuildFailed as error:
        print(error, file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory() as directory:
        lines = theme_test(theme, Path(directory))
    for line in lines:
        print(line)
    return int(any(line.startswith("fail ") for line in lines))


if __name__ == "__main__":
    sys.exit(main())
