"""`rule test` and `rule adopt`: test a rule proposed from a comment, then adopt it on probation."""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from ai_docs_kit.checks.engine import CheckContext, run_checks
from ai_docs_kit.model import Document, Rule, Section
from ai_docs_kit.render.compose import ComposeError, Composition, compose
from ai_docs_kit.source.parser import parse
from ai_docs_kit.source.read import read_source
from ai_docs_kit.theme import Theme, ThemeError, load_theme
from ai_docs_kit.theme.rules import _check_kind, load_theme_rules

SECTION_FIELDS = ("title", "paragraphs", "items", "spoken")


class RuleError(Exception):
    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


def add_rule_commands(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    rule = subparsers.add_parser("rule", help="test and adopt a rule proposed from a comment")
    commands = rule.add_subparsers(dest="rule_command", required=True)
    test = commands.add_parser("test", help="check a rule fires on its example and on no approved exemplar")
    test.add_argument("rule", type=Path, help="the proposed rule (YAML)")
    test.add_argument("--example", required=True, help="<version folder>/<section id> the rule must fire on")
    test.add_argument("--theme", type=Path, default=None, help="theme folder (default: the neutral theme)")
    adopt = commands.add_parser("adopt", help="write a tested rule into the theme on probation")
    adopt.add_argument("rule", type=Path, help="the proposed rule (YAML)")
    adopt.add_argument("--theme", type=Path, required=True, help="theme folder")


def _theme(folder: Path | None) -> Theme:
    from ai_docs_kit.theme import neutral_theme

    try:
        return neutral_theme() if folder is None else load_theme(folder)
    except ThemeError as error:
        raise RuleError(str(error), 2) from error


def _load_rule(path: Path) -> Rule:
    if not path.is_file():
        raise RuleError(f"{path}: no such rule file", 2)
    try:
        rule = Rule.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        _check_kind(rule.check)
    except (OSError, UnicodeDecodeError, yaml.YAMLError, ValueError) as error:
        raise RuleError(f"{path}: not a valid rule: {' '.join(str(error).split())}", 2) from error
    return rule


def _fires(rule: Rule, doc: Document, theme: Theme, composition: Composition | None = None) -> list[str]:
    """The ids of the sections the rule fires on, whatever its own status."""
    probe = rule.model_copy(update={"status": "probation"})
    try:
        if composition is None and rule.scope.components is not None:
            composition = compose(doc)
        findings = run_checks([probe], CheckContext(doc, theme=theme, composition=composition))
    except (ComposeError, re.error, KeyError) as error:
        detail = error.args[0] if isinstance(error, KeyError) and error.args else error
        raise RuleError(f"{rule.id}: the check cannot run: {' '.join(str(detail).split())!r}", 2) from error
    return [f.section_id or "-" for f in findings]


def _example(spec: str) -> tuple[Path, str]:
    folder, _, section_id = spec.rpartition("/")
    # Stop at the version before Path can normalise any part of the section id.
    for index, character in enumerate(spec):
        if character == "/" and index:
            candidate = spec[:index]
            if (Path(candidate) / "composition.json").is_file():
                folder, section_id = candidate, spec[index + 1 :]
                break
    if not folder or not section_id:
        raise RuleError(f"{spec}: --example must be <version folder>/<section id>", 2)
    return Path(folder), section_id


def _example_doc(folder: Path, section_id: str) -> tuple[Document, Composition]:
    path = folder / "composition.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        fmt = data["format"]
        sections = data["sections"]
        if not isinstance(sections, list) or any(not isinstance(s, dict) for s in sections):
            raise ValueError("sections must be a list of objects")
        entry = next((s for s in sections if s.get("id") == section_id), None)
        props = None if entry is None else entry["props"]
        intent = "body" if entry is None else entry.get("intent") or "body"
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise RuleError(f"{path}: cannot read the version: {' '.join(str(error).split())}", 2) from error
    if props is None:
        raise RuleError(f"{section_id}: no such section in {folder}", 2)
    kept: dict[str, Any] = {k: props[k] for k in SECTION_FIELDS if k in props}
    try:
        section = Section.model_validate({"id": section_id, "intent": intent, **kept})
        # Keep the stored component, aligned with the selected section rather than the whole version.
        composition = Composition.model_validate({"format": fmt, "sections": [entry]})
    except ValidationError as error:
        raise RuleError(f"{section_id}: cannot read the section: {' '.join(str(error).split())}", 2) from error
    for item in section.items:
        # Composition uses an empty string for the absent head that source checks skip.
        if item.head == "":
            item.head = None
    return Document(front={}, format=fmt, sections=[section]), composition


def _stamp(rule: Rule) -> str:
    return hashlib.sha256(rule.model_dump_json(by_alias=True).encode()).hexdigest()


def _tested_marker(theme: Theme, rule: Rule) -> Path:
    return theme.root / "rules" / ".tested" / _stamp(rule)


def _ignore_markers(rules: Path) -> None:
    """Keep `.tested/` out of git: list it in `rules/.gitignore` once."""
    ignore = rules / ".gitignore"
    lines = ignore.read_text(encoding="utf-8").splitlines() if ignore.is_file() else []
    if ".tested/" not in (line.strip() for line in lines):
        ignore.write_text("\n".join([*lines, ".tested/"]) + "\n", encoding="utf-8")


def run_test(rule_path: Path, example: str, theme_folder: Path | None) -> int:
    rule = _load_rule(rule_path)
    theme = _theme(theme_folder)
    folder, section_id = _example(example)
    # The neutral theme belongs to the plugin and is read-only in use: only a named theme keeps a marker.
    marker = _tested_marker(theme, rule) if theme_folder is not None else None
    if marker is not None:
        marker.unlink(missing_ok=True)
    problems: list[str] = []
    doc, composition = _example_doc(folder, section_id)
    if section_id not in _fires(rule, doc, theme, composition):
        problems.append(f"misses the example {folder.name}/{section_id}")
    for path in sorted((theme.root / "exemplars" / "gold").glob("*.md")):
        doc, _ = parse(read_source(path, errors="replace"))
        problems += [f"hits the approved exemplar {path.name} {hit}" for hit in _fires(rule, doc, theme)]
    for problem in problems:
        print(f"{rule.id} {problem}")
    if problems:
        return 1
    if marker is not None:
        marker.parent.mkdir(parents=True, exist_ok=True)
        _ignore_markers(marker.parent.parent)
        marker.write_text(rule.id, encoding="utf-8")
    print(f"{rule.id} fires on {folder.name}/{section_id} and on no approved exemplar")
    return 0


def run_adopt(rule_path: Path, theme_folder: Path) -> int:
    rule = _load_rule(rule_path)
    theme = _theme(theme_folder)
    if not _tested_marker(theme, rule).is_file():
        print(f"{rule.id}: not adopted: it has not passed `rule test` against this theme", file=sys.stderr)
        return 1
    adopted = rule.model_copy(update={"origin": "feedback", "status": "probation"})
    target = theme.root / "rules" / "learned" / f"{adopted.id}.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    original = target.read_bytes() if target.exists() else None
    data = json.loads(adopted.model_dump_json(by_alias=True, exclude_none=True))
    target.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    try:
        load_theme_rules(load_theme(theme.root))
    except ThemeError as error:
        if original is None:
            target.unlink()
        else:
            target.write_bytes(original)
        print(f"{rule.id}: not adopted: {error}", file=sys.stderr)
        return 1
    print(f"{adopted.id}: adopted on probation: {target}")
    return 0


def run_rule(args: argparse.Namespace) -> int:
    try:
        if args.rule_command == "test":
            return run_test(args.rule, args.example, args.theme)
        return run_adopt(args.rule, args.theme)
    except RuleError as error:
        print(error, file=sys.stderr)
        return error.code
