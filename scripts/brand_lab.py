"""Run brand setup against an owner's local materials."""

import argparse
import contextlib
import io
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from ai_docs_kit.brand.changes import change_log
from ai_docs_kit.brand.git import run_git
from ai_docs_kit.brand.questions import open_questions
from ai_docs_kit.brand.work import work_dir
from ai_docs_kit.brand.workspace import MATERIAL_CLASSES
from ai_docs_kit.cli import main as cli_main

STEPS = (
    "intake",
    "fonts",
    "gaps",
    "parse",
    "templates",
    "segment",
    "extract",
    "measure",
    "tie",
    "reconcile",
    "synthesise",
    "specimen",
)
StepStatus = Literal["ok", "skipped", "questions", "failed", "not run"]


@dataclass
class StepResult:
    step: str
    status: StepStatus
    code: int | None = None
    output: str = ""
    reason: str = ""
    questions: list[str] = field(default_factory=list)


def default_lab() -> Path:
    return Path.home() / "Documents" / "ai_docs_kit-brand-lab"


def run_command(argv: list[str]) -> tuple[int, str]:
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
        try:
            code = cli_main(argv)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
            if exc.code is not None and not isinstance(exc.code, int):
                print(exc.code, file=sys.stderr)
        except Exception as exc:
            code = 1
            print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
    return code, captured.getvalue()


def copy_materials(lab: Path, brand: Path) -> tuple[list[str], list[str], list[str]]:
    copied: list[str] = []
    unchanged: list[str] = []
    ignored: list[str] = []
    for entry in sorted(lab.iterdir()):
        if entry.name not in MATERIAL_CLASSES or not entry.is_dir():
            ignored.append(entry.name)
            continue
        for source in sorted(entry.rglob("*")):
            relative = source.relative_to(entry)
            if any(part.startswith(".") for part in relative.parts) or not source.is_file():
                continue
            target = brand / "materials" / entry.name / relative
            name = target.relative_to(brand).as_posix()
            if target.is_file() and target.read_bytes() == source.read_bytes():
                unchanged.append(name)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                copied.append(name)
    return copied, unchanged, ignored


def skip_reason(step: str, brand: Path) -> str | None:
    if step == "fonts":
        folder, extensions, reason = brand / "materials/fonts", {".ttf", ".otf"}, "no font files"
    elif step == "templates":
        folder, extensions, reason = (
            brand / "materials",
            {".pptx", ".potx", ".docx", ".dotx"},
            "no PowerPoint or Word files",
        )
    else:
        return None
    return None if any(p.is_file() and p.suffix.lower() in extensions for p in folder.rglob("*")) else reason


def blocking_open(brand: Path) -> set[str]:
    return {question.id for question in open_questions(brand) if question.blocking}


def abandon_change(brand: Path) -> str | None:
    branch = run_git(brand, "branch", "--show-current").strip()
    if branch == "main":
        return None
    run_git(brand, "reset", "--hard")
    run_git(brand, "clean", "-fd")
    run_git(brand, "checkout", "main")
    run_git(brand, "branch", "-D", branch)
    return branch


def _run_step(step: str, slug: str, root: Path, brand: Path, past_questions: bool) -> StepResult:
    reason = skip_reason(step, brand)
    if reason:
        return StepResult(step, "skipped", reason=reason)
    before = blocking_open(brand)
    code, output = run_command(["brand", step, slug, "--root", str(root)])
    output = "\n".join(output.splitlines()[-30:])
    if code:
        branch = abandon_change(brand)
        return StepResult(step, "failed", code, output, f"abandoned branch {branch}" if branch else "")
    new = sorted(blocking_open(brand) - before)
    if new and not past_questions:
        return StepResult(step, "questions", code, output, questions=new)
    return StepResult(step, "ok", code, output)


def _report(
    brand: Path, slug: str, results: list[StepResult], copied: list[str], unchanged: list[str], ignored: list[str]
) -> Path:
    lines = [f"# Brand lab: {slug}", "", f"Materials: {len(copied)} copied, {len(unchanged)} unchanged"]
    lines.extend(f"Ignored: {entry}" for entry in ignored)
    lines.append("")
    stopped = None
    for result in results:
        line = f"- {result.step}: {result.status}"
        if result.status == "failed":
            line += f" (exit {result.code})"
        if result.reason:
            line += f" ({result.reason})"
        if result.status == "questions":
            line += f" (new questions: {', '.join(result.questions)})"
        lines.append(line)
        if result.status in ("failed", "questions"):
            stopped = result
    if stopped:
        lines.extend(["", f"## Output of {stopped.step}", "", stopped.output])
    lines.extend(["", "## Open questions", ""])
    for question in open_questions(brand):
        label = "blocking" if question.blocking else "not blocking"
        lines.append(f"- {question.id} [{label}]: {question.text}")
    lines.extend(["", "## Changes", "", f"{len(change_log(brand))} brand changes", ""])
    path = work_dir(brand) / "lab/report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug")
    parser.add_argument("--lab", type=Path, default=default_lab())
    parser.add_argument("--root", type=Path, default=Path.cwd() / ".brand")
    parser.add_argument("--from", dest="start", choices=STEPS, default="intake")
    parser.add_argument("--past-questions", action="store_true")
    args = parser.parse_args(argv)
    lab = args.lab / args.slug
    if not lab.is_dir():
        print(f"no lab folder: {lab}", file=sys.stderr)
        return 2
    brand = args.root / args.slug
    if not (brand / ".git").exists():
        code, output = run_command(["brand", "init", args.slug, "--root", str(args.root)])
        if code:
            print(output, file=sys.stderr)
            return 2
    copied, unchanged, ignored = copy_materials(lab, brand)
    results = []
    stopped = False
    start = STEPS.index(args.start)
    for index, step in enumerate(STEPS):
        if index < start or stopped:
            results.append(StepResult(step, "not run"))
            continue
        result = _run_step(step, args.slug, args.root, brand, args.past_questions)
        results.append(result)
        print(f"{step}  {result.status}")
        stopped = result.status in ("failed", "questions")
    path = _report(brand, args.slug, results, copied, unchanged, ignored)
    print(f"report: {path}")
    return 2 if any(r.status == "failed" for r in results) else 1 if stopped else 0


if __name__ == "__main__":
    raise SystemExit(main())
