"""Issue 377: one working-file theme decision shared by the API, commands and skills."""

import json
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from ai_docs_kit import cli
from ai_docs_kit import theme as theme_api

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = (
    "folder-before-slug",
    "folder-before-neutral",
    "external-path",
    "slug",
    "neutral",
    "no-brands",
    "single-brand",
)
BRANDED = tuple(case for case in SCENARIOS if case not in ("neutral", "no-brands"))
MARKER_RULE = "house.theme-marker"
BODY = """
## Sources

- [S1] trial-notes.txt, trial observations

::: {#a7c31 .section intent="body"}
## Trial scope

The trial retains the calibration marker. [S1]
:::
"""


def _run(cwd, *args):
    return subprocess.run(
        [sys.executable, "-m", "ai_docs_kit.cli", *map(str, args)],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _theme_copy(folder, name):
    shutil.copytree(theme_api.NEUTRAL_ROOT, folder, dirs_exist_ok=True)
    info = yaml.safe_load((folder / "theme.yaml").read_text(encoding="utf-8"))
    info["name"] = name
    (folder / "theme.yaml").write_text(yaml.safe_dump(info), encoding="utf-8")
    rule = {
        "id": MARKER_RULE,
        "title": "Identify the selected test theme",
        "origin": "manual",
        "strength": "hard",
        "status": "active",
        "severity": "error",
        "tier": "source",
        "provenance": {"by": "Synthetic fixture author"},
        "check": {"kind": "text-pattern", "field": "paragraphs", "regex": "calibration marker"},
        "remedy": {"class": "redraft", "hint": "Remove the test marker"},
    }
    rules = folder / "rules" / "authored"
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "theme-marker.yaml").write_text(yaml.safe_dump(rule), encoding="utf-8")
    return folder


def _brand(project, slug, root=None):
    root = root if root is not None else project / ".brand"
    assert cli.main(["brand", "init", slug, "--root", str(root)]) == 0
    return _theme_copy(root / slug / "theme", slug)


def _write(source, value=None, *, reverse=False):
    front = {"doctype": "report", "format": "doc", "title": "Trial findings", "locale": "en-GB"}
    if value is not None:
        front["theme"] = value
    if reverse:
        front = dict(reversed(list(front.items())))
    source.write_text("---\n" + yaml.safe_dump(front, sort_keys=False) + "---\n" + BODY, encoding="utf-8")


@dataclass
class Case:
    source: Path
    caller: Path
    folder: Path
    value: str | None


def _case(tmp_path, scenario, reverse=False):
    project = tmp_path / "project with spaces"
    project.mkdir()
    caller = tmp_path / "caller"
    caller.mkdir()
    # A brand in the caller's folder must never affect this working file.
    _brand(caller, "caller-brand")
    brands = {}
    if scenario != "no-brands":
        slugs = ["harbour"] if scenario == "single-brand" else ["harbour", "bracken"]
        for slug in reversed(slugs) if reverse else slugs:
            brands[slug] = _brand(project, slug)
    value = None
    folder = theme_api.NEUTRAL_ROOT
    if scenario == "single-brand":
        folder = brands["harbour"]
    elif scenario == "slug":
        value, folder = "harbour", brands["harbour"]
        # A directory without a theme is not the explicit theme-folder branch.
        (project / "harbour").mkdir()
    elif scenario.startswith("folder-before-"):
        value = "harbour" if scenario == "folder-before-slug" else "neutral"
        folder = _theme_copy(project / value, "path-choice")
    elif scenario == "external-path":
        folder = _brand(project, "offsite", tmp_path / "shared brands")
        value = "../shared brands/offsite/theme"
    elif scenario == "neutral":
        value = "neutral"
    source = project / "note.md"
    _write(source, value, reverse=reverse)
    return Case(source, caller, folder, value)


def _resolver():
    resolver = getattr(theme_api, "resolve_theme", None)
    assert callable(resolver), "ai_docs_kit.theme must expose resolve_theme(path)"
    return resolver


def _selection(value):
    # The issue specifies the two values, rather than a particular Python container
    # or the JSON spelling of the folder field.
    names = ("path", "folder", "root", "theme", "theme_path")
    rule_names = ("rule", "reason")
    if isinstance(value, Mapping):
        fields = [key for key in names if key in value]
        rules = [key for key in rule_names if key in value]
        assert len(fields) == len(rules) == 1, value
        folder, rule = value[fields[0]], value[rules[0]]
    elif any(hasattr(value, key) for key in rule_names):
        fields = [key for key in names if hasattr(value, key)]
        rules = [key for key in rule_names if hasattr(value, key)]
        assert fields and rules, value
        folder, rule = getattr(value, fields[0]), getattr(value, rules[0])
    else:
        assert isinstance(value, (tuple, list)) and len(value) == 2, value
        folder, rule = value
    assert isinstance(folder, (str, Path)), value
    assert isinstance(rule, str) and rule.strip(), value
    return Path(folder), rule


def _absolute(folder, source):
    return (folder if folder.is_absolute() else source.parent / folder).resolve()


def _assert_selection(folder, rule, case):
    assert _absolute(folder, case.source) == case.folder.resolve()
    if case.value is not None:
        assert "front matter" in rule.lower(), rule
    elif case.folder == theme_api.NEUTRAL_ROOT:
        assert "neutral" in rule.lower(), rule
    else:
        assert "brand" in rule.lower(), rule


@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize("reverse", [False, True], ids=["front-order", "reversed-front-and-brand-order"])
def test_resolve_theme_returns_the_folder_and_its_rule(tmp_path, monkeypatch, scenario, reverse):
    case = _case(tmp_path, scenario, reverse)
    monkeypatch.chdir(case.caller)
    folder, rule = _selection(_resolver()(case.source))
    _assert_selection(folder, rule, case)


@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize("reverse", [False, True], ids=["front-order", "reversed-front-and-brand-order"])
def test_theme_which_prints_the_same_decision_as_text_and_json(tmp_path, monkeypatch, scenario, reverse):
    case = _case(tmp_path, scenario, reverse)
    plain = _run(case.caller, "theme", "which", case.source)
    assert plain.returncode == 0, plain.stderr
    assert plain.stderr == ""
    lines = plain.stdout.splitlines()
    assert len(lines) == 1, plain.stdout
    match = re.fullmatch(r"(.+) \((.+)\)", lines[0])
    assert match, plain.stdout
    folder, rule = Path(match[1]), match[2]
    _assert_selection(folder, rule, case)

    machine = _run(case.caller, "theme", "which", case.source, "--json")
    assert machine.returncode == 0, machine.stderr
    assert machine.stderr == ""
    payload = json.loads(machine.stdout)
    assert isinstance(payload, dict), payload
    json_folder, json_rule = _selection(payload)
    assert _absolute(json_folder, case.source) == _absolute(folder, case.source)
    assert json_rule == rule
    monkeypatch.chdir(case.caller)
    api_folder, api_rule = _selection(_resolver()(case.source))
    assert _absolute(api_folder, case.source) == _absolute(folder, case.source)
    assert api_rule == rule


def test_theme_which_help_answers(tmp_path):
    done = _run(tmp_path, "theme", "which", "--help")
    assert done.returncode == 0, done.stderr
    assert "--json" in done.stdout
    assert "usage:" in done.stdout and "which" in done.stdout
    assert done.stderr == ""


@pytest.mark.parametrize("command", ["which", "build", "check"])
@pytest.mark.parametrize(
    ("value", "scenario", "candidates"),
    [
        ("missing-theme", "no-brands", ()),
        ("missing-theme", "single-brand", ("harbour",)),
        ("missing-theme", "slug", ("harbour", "bracken")),
        (None, "slug", ("harbour", "bracken")),
    ],
    ids=["unknown-with-no-brand", "unknown-with-one-brand", "unknown-with-two-brands", "ambiguous-brands"],
)
@pytest.mark.parametrize("reverse", [False, True], ids=["brand-order", "reversed-brand-order"])
def test_unresolved_theme_is_one_exit_2_line_naming_candidates(tmp_path, command, value, scenario, candidates, reverse):
    case = _case(tmp_path, scenario, reverse)
    _write(case.source, value, reverse=reverse)
    args = ["theme", "which"] if command == "which" else [command]
    done = _run(case.caller, *args, case.source)
    assert done.returncode == 2, done.stdout + done.stderr
    lines = done.stderr.splitlines()
    assert len(lines) == 1, done.stderr
    assert all(candidate in lines[0] for candidate in candidates), done.stderr
    assert "caller-brand" not in lines[0], done.stderr
    assert "Traceback" not in done.stderr
    if value is not None:
        assert value in lines[0] and "neutral" in lines[0], done.stderr


@pytest.mark.parametrize("scenario", BRANDED)
def test_build_records_the_resolved_theme_and_explicit_theme_still_wins(tmp_path, scenario):
    case = _case(tmp_path, scenario, reverse=scenario in ("slug", "external-path"))
    # The explicit control must work even when the source cannot be resolved.
    original = case.source.read_text(encoding="utf-8")
    _write(case.source, "missing-theme")
    control = _run(case.caller, "build", case.source, "--theme", theme_api.NEUTRAL_ROOT)
    assert control.returncode == 0, control.stderr + control.stdout
    versions = case.source.with_suffix(".versions")
    neutral = json.loads((versions / "v1" / "manifest.json").read_text(encoding="utf-8"))
    assert neutral["theme"]["name"] == "neutral"
    assert (versions / "v1" / "note.pdf").is_file()

    case.source.write_text(original, encoding="utf-8")
    built = _run(case.caller, "build", case.source)
    assert built.returncode == 0, built.stderr + built.stdout
    manifest = json.loads((versions / "v2" / "manifest.json").read_text(encoding="utf-8"))
    expected = yaml.safe_load((case.folder / "theme.yaml").read_text(encoding="utf-8"))
    assert manifest["theme"]["name"] == expected["name"], "build silently used a different theme"
    assert manifest["theme"]["version"] == expected["version"]
    assert (versions / "v2" / "note.pdf").is_file()


@pytest.mark.parametrize("scenario", BRANDED)
def test_check_runs_the_resolved_themes_rules_and_explicit_theme_still_wins(tmp_path, scenario):
    case = _case(tmp_path, scenario, reverse=scenario in ("slug", "external-path"))
    original = case.source.read_text(encoding="utf-8")
    # Establish that the fixture's rule fires through the real command.
    _write(case.source, "neutral")
    branded = _run(case.caller, "check", case.source, "--theme", case.folder)
    assert branded.returncode == 1, branded.stderr + branded.stdout
    report = case.source.parent / "build" / "note.findings.json"
    assert any(f["rule_id"] == MARKER_RULE for f in json.loads(report.read_text(encoding="utf-8")))
    # A missing key with several brands must not defeat an explicit override.
    _write(case.source)
    control = _run(case.caller, "check", case.source, "--theme", theme_api.NEUTRAL_ROOT)
    assert control.returncode == 0, control.stderr + control.stdout
    assert not any(f["rule_id"] == MARKER_RULE for f in json.loads(report.read_text(encoding="utf-8")))

    case.source.write_text(original, encoding="utf-8")
    checked = _run(case.caller, "check", case.source)
    assert checked.returncode == 1, checked.stderr + checked.stdout
    findings = json.loads(report.read_text(encoding="utf-8"))
    assert [(f["rule_id"], f["section_id"]) for f in findings if f["rule_id"] == MARKER_RULE] == [
        (MARKER_RULE, "a7c31")
    ]


@pytest.mark.parametrize("command", ["build", "check"])
def test_file_commands_call_the_shared_resolver(tmp_path, monkeypatch, command):
    case = _case(tmp_path, "single-brand")
    resolver = _resolver()
    calls = []

    def recorded(path):
        calls.append(Path(path).resolve())
        return resolver(path)

    monkeypatch.setattr(theme_api, "resolve_theme", recorded)
    # Permit module-qualified calls, including through the defining submodule,
    # as well as an import of the public function into the command module.
    for module in (sys.modules[resolver.__module__], cli):
        for name, value in list(vars(module).items()):
            if value is resolver:
                monkeypatch.setattr(module, name, recorded)
    monkeypatch.chdir(case.caller)
    code = cli.main([command, str(case.source)])
    assert code in (0, 1)
    assert case.source.resolve() in calls, f"{command} did not call resolve_theme"


@pytest.mark.parametrize("relative", ["skills/create/survey.md", "skills/create/draft.md", "skills/review/SKILL.md"])
def test_skills_delegate_the_theme_decision_to_the_command(relative):
    text = (ROOT / relative).read_text(encoding="utf-8")
    assert re.search(r"ai-docs-kit theme which\s+\S+", text), f"{relative} must call theme which for the working file"
    assert not re.search(
        r"\.brand/<slug>/theme[^.\n]*if one exists[^.\n]*otherwise[^.\n]*neutral", text, re.IGNORECASE
    ), f"{relative} still describes its own resolution order"


def test_design_documents_the_changed_default_and_the_refusal():
    text = (ROOT / "docs/DESIGN.md").read_text(encoding="utf-8")
    assert "ai-docs-kit theme which" in text, "DESIGN.md must explain the shared theme decision"
    assert "--theme" in text
    assert re.search(r"front matter[^\n]*theme|theme[^\n]*front matter", text, re.IGNORECASE)
    assert re.search(r"single brand|one brand|exactly one", text, re.IGNORECASE)
    assert re.search(r"several brands|multiple brands|two or more|more than one brand", text, re.IGNORECASE)
