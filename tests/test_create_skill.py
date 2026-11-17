import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from tests.support.fixtures import fixture_path
from tests.test_skills_lint import COMMAND, help_exit_code, lint

ROOT = Path(__file__).resolve().parent.parent
CREATE = ROOT / "skills" / "create"
AGENTS = ROOT / "agents"
STAGES = ("survey", "gather", "outline", "draft", "look", "ship")
AGENT_NAMES = ("gather", "write-section", "look")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def stage(name: str) -> Path:
    found = sorted(p for p in CREATE.rglob(f"{name}.md") if p.name != "SKILL.md")
    assert found, f"no stage file for {name} under skills/create"
    return found[0]


def agent(name: str) -> str:
    return read(AGENTS / f"{name}.md")


def run(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "ai_docs_kit.cli", *args], capture_output=True, text=True, cwd=cwd)


@pytest.mark.parametrize("name", STAGES)
def test_each_stage_file_exists_and_is_named_by_the_skill(name):
    assert name in read(CREATE / "SKILL.md")
    text = read(stage(name))
    assert "Stub" not in text
    assert len(text.split()) > 40


def test_skill_is_no_longer_a_stub():
    assert "Stub" not in read(CREATE / "SKILL.md")


@pytest.mark.parametrize("name", STAGES)
def test_every_command_a_stage_file_names_exists(name):
    text = read(stage(name))
    commands = set(COMMAND.findall(text))
    assert commands or name in ("survey", "outline")
    assert [c for c in commands if help_exit_code(c) != 0] == []


def test_the_outline_is_the_one_stop():
    skill = read(CREATE / "SKILL.md")
    assert re.search(r"one stop|only stop|single stop", skill, re.IGNORECASE)
    assert re.search(r"outline", read(stage("outline")), re.IGNORECASE)
    assert re.search(r"agree|approv|confirm", read(stage("outline")), re.IGNORECASE)
    for name in ("draft", "look", "ship"):
        assert re.search(r"do not (stop|ask)|without (stopping|asking)|never (stop|ask)", read(stage(name)), re.I)


@pytest.mark.parametrize("name", AGENT_NAMES)
def test_agent_states_input_output_and_what_it_never_does(name):
    text = agent(name)
    assert "Stub" not in text
    assert lint(AGENTS / f"{name}.md") == []
    for heading in ("Input", "Output", "Never"):
        assert re.search(rf"^#+ .*{heading}", text, re.MULTILINE | re.IGNORECASE), f"{name}: no {heading} heading"


def test_look_agent_returns_a_json_array_only():
    text = agent("look")
    assert re.search(r"JSON array", text)
    assert re.search(r"only", text, re.IGNORECASE)
    for key in ("severity", "rule", "page", "section", "message"):
        assert key in text


def test_write_section_reads_and_writes_through_section_commands():
    text = agent("write-section")
    assert "ai-docs-kit section get" in text
    assert "ai-docs-kit section put" in text


def test_look_stage_bounds_the_fix_rounds_and_reports_by_section():
    text = read(stage("look"))
    assert re.search(r"at most two|no more than two|up to two|two (fix )?rounds", text, re.IGNORECASE)
    assert re.search(r"by section", text, re.IGNORECASE)
    assert "--findings" in text
    assert "--pages" in text


def test_ship_marks_sent_only_through_the_command():
    text = read(stage("ship"))
    assert "ai-docs-kit sent" in text
    for name in STAGES:
        body = read(stage(name))
        assert not re.search(r"(edit|write|change)[^.\n]*manifest\.json", body, re.IGNORECASE)


@pytest.mark.parametrize("name", ["draft", "look"])
def test_stages_that_change_text_do_so_through_section_put(name):
    text = read(stage(name))
    assert "ai-docs-kit section put" in text
    assert re.search(r"never (edit|write)[^.\n]*working file|only (through|with)[^.\n]*section put", text, re.I)


def test_agents_never_write_the_working_file_directly():
    for name in AGENT_NAMES:
        assert re.search(r"never[^.\n]*(write|edit)[^.\n]*(working file|file)", agent(name), re.IGNORECASE), name


def test_the_chain_the_stages_describe_runs_on_a_fixture(tmp_path):
    shutil.copyfile(fixture_path("doc", "report.md"), tmp_path / "report.md")
    working = tmp_path / "report.md"
    assert run("build", str(working), cwd=tmp_path).returncode == 0
    version = tmp_path / "report.versions" / "v1"
    pages = json.loads((version / "pages" / "pages.json").read_text())["pages"]
    section = pages[0]["sections"][0]
    listing = run("section", "list", str(working), cwd=tmp_path)
    assert listing.returncode == 0
    finding = [{"severity": "warning", "rule": "look.crowded", "page": 1, "section": section, "message": "Too tight."}]
    findings = tmp_path / "findings.json"
    findings.write_text(json.dumps(finding))
    assert run("look", str(version), "--findings", str(findings), cwd=tmp_path).returncode == 0
    got = run("section", "get", str(working), section, cwd=tmp_path)
    assert got.returncode == 0
    block = tmp_path / "block.md"
    block.write_text(re.search(r"^:::.*?^:::\s*$", got.stdout, re.MULTILINE | re.DOTALL).group(0) + "\n")
    put = run("section", "put", str(working), section, "--from", str(block), cwd=tmp_path)
    assert put.returncode in (0, 1), put.stderr
    assert run("build", str(working), cwd=tmp_path).returncode == 0
    latest = sorted((tmp_path / "report.versions").glob("v*"))[-1]
    clean = tmp_path / "clean.json"
    clean.write_text("[]")
    assert run("look", str(latest), "--findings", str(clean), cwd=tmp_path).returncode == 0
    sent = run("sent", str(latest), "--to", "a person", cwd=tmp_path)
    assert sent.returncode == 0, sent.stderr + sent.stdout
    manifest = json.loads((latest / "manifest.json").read_text())
    assert "a person" in json.dumps(manifest)
