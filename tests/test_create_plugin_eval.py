"""Offline acceptance checks for issue 281, without invoking a model.

Oracle: issue 223's research comment and the plugin-evals reference at
https://code.claude.com/docs/en/plugin-evals.md. Regex probes use the syntax
shared by Python and JavaScript, so these checks need no additional runtime.
"""

import copy
import fnmatch
import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
EVALS = ROOT / "evals"


def _markdown(path):
    assert path.is_file(), f"missing eval file: {path}"
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, re.S)
    assert match, f"{path} needs YAML front matter"
    meta = yaml.safe_load(match[1])
    assert isinstance(meta, dict), f"{path} front matter must be a mapping"
    return meta, text[match.end() :].strip()


def _cases(root=EVALS):
    found = sorted({p.parent for name in ("prompt.md", "case.yaml") for p in root.rglob(name)})
    assert found, "add the create eval under evals/<case>/"
    return found


def _structure(root):
    for case in _cases(root):
        _, prompt = _markdown(case / "prompt.md")
        assert prompt, f"{case}: empty prompt"
        graders = sorted((case / "graders").glob("*.md"))
        assert graders, f"{case}: at least one grader is required"
        for grader in graders:
            meta, _ = _markdown(grader)
            assert meta.get("type") in {"regex", "tool_used", "tool_order", "file_exists", "llm", "baseline"}


def _case():
    cases = _cases()
    assert len(cases) == 1, "issue 281 ships one create case"
    return cases[0]


def _graders(case):
    paths = sorted((case / "graders").glob("*.md"))
    assert paths, "the create case needs graders"
    return [_markdown(path)[0] for path in paths]


def _passes(graders, text):
    """Probe the deterministic regex conditions, including negative/count checks."""
    assert graders, "missing file-content regex grader"
    for grader in graders:
        pattern = grader.get("pattern")
        assert isinstance(pattern, str) and pattern.strip(), "regex graders need a pattern"
        flags = grader.get("flags", "")
        options = (re.I if "i" in flags else 0) | (re.M if "m" in flags else 0) | (re.S if "s" in flags else 0)
        matches = list(re.finditer(pattern, text, options))
        mode = grader.get("match", "contains")
        if mode == "not_contains":
            passed = not matches
        elif mode.startswith("count:"):
            passed = len(matches) == int(mode.split(":", 1)[1])
        else:
            assert mode == "contains", f"unknown regex match mode: {mode}"
            passed = bool(matches)
        if not passed:
            return False
    return True


def test_eval_suite_structure_is_checked_offline(tmp_path):
    _structure(EVALS)

    # Both missing-file directions must be detected, not silently undiscovered.
    case = tmp_path / "seeded-case"
    (case / "graders").mkdir(parents=True)
    (case / "case.yaml").write_text('schema_version: "1.1"\nname: seeded-case\n', encoding="utf-8")
    with pytest.raises(AssertionError, match="missing eval file"):
        _structure(tmp_path)
    prompt = case / "prompt.md"
    prompt.write_text("---\ntags: [smoke]\n---\nWrite a report.\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="at least one grader"):
        _structure(tmp_path)
    (case / "graders" / "result.md").write_text("---\ntype: regex\npattern: report\n---\n", encoding="utf-8")
    _structure(tmp_path)
    prompt.unlink()
    with pytest.raises(AssertionError, match="missing eval file"):
        _structure(tmp_path)


def test_create_case_starts_from_three_sources_and_agrees_the_outline(tmp_path):
    case = _case()
    meta, prompt = _markdown(case / "prompt.md")
    config_path = case / "case.yaml"
    assert config_path.is_file(), "the case needs context.scaffold_script in case.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert config.get("schema_version") == "1.1"
    assert config.get("name")
    execution = {**config.get("execution", {}), **meta}
    agreement = execution.get("append_system_prompt", "")
    assert re.search(r"agree|accept|approv", agreement, re.I)
    assert re.search(r"first[^.\n]*outline", agreement, re.I)
    assert re.search(r"\bshort\b|\bbrief\b|\bconcise\b", prompt, re.I)
    assert re.search(r"\breport\b", prompt, re.I)
    assert "Skill" in execution.get("allowed_tools", []), "the eval must allow invoking create"
    scaffold_name = config.get("context", {}).get("scaffold_script")
    assert isinstance(scaffold_name, str) and scaffold_name.strip()
    scaffold = (case / scaffold_name).resolve()
    assert scaffold.is_relative_to(case.resolve()) and scaffold.is_file()

    snapshots = []
    for folder in ("workspace", "workspace with spaces"):
        workspace = tmp_path / folder
        workspace.mkdir()
        result = subprocess.run(["bash", str(scaffold)], cwd=workspace, capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, f"scaffold failed: {result.stderr}"
        files = sorted(p for p in workspace.rglob("*") if p.is_file())
        assert len(files) == 3, "scaffold only three short sources, without a pre-drafted working file or build"
        snapshot = {}
        for path in files:
            content = path.read_text(encoding="utf-8")
            assert 3 <= len(content.split()) <= 1000, f"{path.name} should be a short source"
            assert not re.search(r"(?m)^:::\s*\{#|^doctype:\s*report", content), "do not seed a working file"
            assert not any(part in {"build", ".ai_docs_kit"} or part.endswith(".versions") for part in path.parts)
            snapshot[str(path.relative_to(workspace))] = content
        snapshots.append(snapshot)
    assert snapshots[0] == snapshots[1], "scaffolding must be reproducible in either working directory"


def test_graders_require_create_outputs_a_clean_look_and_three_cited_sections():
    graders = _graders(_case())
    skills = [g for g in graders if g.get("type") == "tool_used" and g.get("tool") == "Skill"]
    assert skills, "grade invocation of create through Skill"
    assert all(g.get("min", 1) >= 1 for g in skills), "the skill grader must require an invocation"
    for name in ("create", "ai-docs-kit:create"):
        assert any(re.search(g.get("input_match", r"(?!)"), json.dumps({"skill": name})) for g in skills)
    for name in ("review", "brand", "recreate"):
        assert not any(re.search(g.get("input_match", r"(?!)"), json.dumps({"skill": name})) for g in skills)

    paths = [g.get("path", "") for g in graders if g.get("type") == "file_exists" and g.get("exists", True)]
    for output in ("build/report.pdf", "build/report.docx", "report.versions/v1/manifest.json"):
        assert any(fnmatch.fnmatchcase(output, pattern) for pattern in paths), f"missing output grader for {output}"

    regexes = [g for g in graders if g.get("type") == "regex"]
    assert all(isinstance(g.get("target"), dict) and g["target"].get("source") == "file" for g in regexes)
    manifests = [g for g in regexes if g["target"].get("path", "").endswith("manifest.json")]
    working = [g for g in regexes if g["target"].get("path", "").endswith(".md")]
    assert manifests and working, "grade the manifest and working file contents, rather than the final reply"

    good = {"findings": {"error": 0, "warning": 0, "info": 0}, "look": {"pages": 1, "clean": True, "agent": []}}
    bad_engine = copy.deepcopy(good)
    bad_engine["findings"]["error"] = 1
    bad_agent = copy.deepcopy(good)
    bad_agent["look"]["clean"] = False
    bad_agent["look"]["agent"] = [
        {"severity": "error", "rule": "layout", "page": 1, "section": "a1", "message": "Text clipped"}
    ]
    # Key order and JSON whitespace must not decide whether the look is clean.
    for indent in (None, 2):
        for order in (good, dict(reversed(list(good.items())))):
            assert _passes(manifests, json.dumps(order, indent=indent)), "accept a recorded clean look"
        for defect in ({"findings": good["findings"]}, {**good, "look": None}, bad_engine, bad_agent):
            assert not _passes(manifests, json.dumps(defect, indent=indent)), "reject a missing look or open error"

    sources = "## Sources\n\n- [S1] notes.txt\n- [S2] results.txt\n- [S3] next-steps.txt\n\n"

    def section(index, citation=True, drafted=True):
        body = "The trial supports a further check." if drafted else ""
        cite = f" [S{(index - 1) % 3 + 1}]" if citation else ""
        return f'::: {{#a{index} .section intent="body"}}\n## Finding {index}\n\n{body}{cite}\n:::\n\n'

    for order in ((1, 2, 3), (3, 1, 2)):
        assert _passes(working, sources + "".join(section(i) for i in order))
        for defect in (
            "".join(section(i) for i in order[:2]),
            "".join(section(i, citation=False) for i in order),
            "".join(section(i, drafted=False, citation=False) for i in order),
            "".join(section(i, citation=i != 2) for i in order),
        ):
            assert not _passes(working, sources + defect), "require three drafted sections, each with a citation"
    assert _passes(working, sources + "".join(section(i) for i in (1, 2, 3, 4))), "three is a minimum"


def test_readme_explains_the_owner_run_before_release():
    paths = [ROOT / "README.md", EVALS / "README.md"]
    text = "\n".join(p.read_text(encoding="utf-8") for p in paths if p.is_file())
    command = re.search(
        r"claude plugin eval \.\s+--allow-tools Bash Write Edit\s+--runs 1\s+"
        r"--max-cost-usd\s+(?:\d+(?:\.\d+)?|<[^>]+>)([^\n]*)",
        text,
    )
    assert command, "document the bounded eval command, including the required tool grants"
    assert "--scaffold" in command[0], "the documented run must actually seed the starting folder"
    assert re.search(r"live (?:model |Claude |API )?calls", text, re.I)
    assert re.search(r"owner|person", text, re.I)
    assert re.search(r"not[^.\n]*\bCI\b|\bCI\b[^.\n]*(?:never|must not|does not)", text, re.I)
    assert re.search(r"not[^.\n]*\bloop\b|\bloop\b[^.\n]*(?:never|must not|does not)", text, re.I)
    assert re.search(r"before (?:each|every|a) release|pre-release", text, re.I)
