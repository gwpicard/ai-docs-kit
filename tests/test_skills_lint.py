import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
COMMAND = re.compile(r"`[^`\n]*?ai-docs-kit ([a-z][a-z0-9-]*)")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def skill_files(root: Path) -> list[Path]:
    return sorted(root.glob("skills/*/SKILL.md")) + sorted(root.glob("agents/*.md"))


def help_exit_code(command: str) -> int:
    done = subprocess.run(
        [sys.executable, "-m", "ai_docs_kit.cli", command, "--help"], capture_output=True, text=True, cwd=ROOT
    )
    return done.returncode


def lint(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER.match(text)
    if not match:
        return [f"{path.name}: no frontmatter"]
    meta = yaml.safe_load(match.group(1))
    problems = []
    if not isinstance(meta, dict):
        return [f"{path.name}: frontmatter is not a mapping"]
    for key in ("name", "description"):
        if not meta.get(key):
            problems.append(f"{path.name}: frontmatter lacks {key}")
    for command in sorted(set(COMMAND.findall(text[match.end() :]))):
        if help_exit_code(command) != 0:
            problems.append(f"{path.name}: unknown command {command}")
    return problems


def test_manifests_name_the_plugin():
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert plugin["name"] == "ai-docs-kit"
    assert "ai-docs-kit" in [p["name"] for p in market["plugins"]]


def test_wrapper_passes_arguments_and_exit_code_through(tmp_path):
    wrapper = ROOT / "bin" / "ai-docs-kit"
    assert os.access(wrapper, os.X_OK)
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PLUGIN_ROOT"}
    ok = subprocess.run([str(wrapper), "--help"], capture_output=True, text=True, cwd=tmp_path, env=env)
    assert ok.returncode == 0
    assert "usage: ai-docs-kit" in ok.stdout
    bad = subprocess.run([str(wrapper), "no-such-command"], capture_output=True, text=True, cwd=tmp_path, env=env)
    assert bad.returncode == 2


def test_wrapper_uses_the_plugin_root_when_set(tmp_path):
    env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(ROOT)}
    done = subprocess.run(
        [str(ROOT / "bin" / "ai-docs-kit"), "--version"], capture_output=True, text=True, cwd=tmp_path, env=env
    )
    assert done.returncode == 0


def test_skills_and_agents_exist():
    assert sorted(p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md")) == ["brand", "create", "review"]
    assert list((ROOT / "agents").glob("*.md"))


def test_every_skill_and_agent_file_passes_the_lint():
    files = skill_files(ROOT)
    assert files
    problems = [p for f in files for p in lint(f)]
    assert problems == []


def test_lint_fails_on_a_command_that_does_not_exist(tmp_path):
    skill = tmp_path / "skills" / "bad" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: bad\ndescription: seeded\n---\nRun `ai-docs-kit frobnicate`.\n", encoding="utf-8")
    assert lint(skill)


def test_lint_fails_without_frontmatter(tmp_path):
    skill = tmp_path / "SKILL.md"
    skill.write_text("Run `ai-docs-kit doctor`.\n", encoding="utf-8")
    assert lint(skill)


def test_lint_passes_a_good_file(tmp_path):
    skill = tmp_path / "SKILL.md"
    skill.write_text("---\nname: good\ndescription: ok\n---\nRun `bin/ai-docs-kit doctor`.\n", encoding="utf-8")
    assert lint(skill) == []


@pytest.mark.parametrize("command", ["doctor"])
def test_help_needs_no_api_key_or_anthropic_import(command):
    code = "import sys; from ai_docs_kit.cli import main; sys.modules['anthropic'] = None; main()"
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    done = subprocess.run(
        [sys.executable, "-c", code, command, "--help"], capture_output=True, text=True, env=env, cwd=ROOT
    )
    assert done.returncode == 0, done.stderr
