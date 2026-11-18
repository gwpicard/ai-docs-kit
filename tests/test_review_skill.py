"""The review skill and its classify agent: content, commands named, and the chain they describe."""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from tests.test_skills_lint import COMMAND, help_exit_code, lint

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "review" / "SKILL.md"
AGENT = ROOT / "agents" / "review-classify.md"

SOURCE = """---
doctype: report
format: doc
title: Note
---

::: {#alpha01 .section intent="body"}
## Alpha

Alpha keeps its original wording here.
:::

::: {#beta01 .section intent="body"}
## Beta

Beta holds the second paragraph of the note.
:::
"""


def skill() -> str:
    return SKILL.read_text(encoding="utf-8")


def agent() -> str:
    return AGENT.read_text(encoding="utf-8")


def run(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "ai_docs_kit.cli", *args], capture_output=True, text=True, cwd=cwd)


def test_skill_and_agent_are_no_longer_stubs():
    assert "Stub" not in skill()
    assert "Stub" not in agent()
    assert len(skill().split()) > 150
    assert len(agent().split()) > 60


def test_skill_and_agent_pass_the_lint():
    assert lint(SKILL) == []
    assert lint(AGENT) == []


def test_skill_names_the_commands_of_the_round_trip():
    commands = set(COMMAND.findall(skill()))
    assert {"review", "rule", "build", "look"} <= commands
    assert [c for c in commands if help_exit_code(c) != 0] == []
    text = skill()
    for phrase in ("ai-docs-kit review read", "ai-docs-kit review apply", "ai-docs-kit rule test"):
        assert phrase in text


def test_skill_steps_come_in_the_design_order():
    text = skill().lower()
    marks = ["review read", "classify", "review apply", "redraft", "build", "look"]
    positions = [text.find(m) for m in marks]
    assert -1 not in positions, dict(zip(marks, positions, strict=True))
    assert positions == sorted(positions)
    assert re.search(r"one screen", text)
    assert re.search(r"ask(s)? once|one question|single question|once", text)


def test_skill_reports_every_outcome():
    text = skill().lower()
    for word in ("applied", "redrafted", "declined", "unplaced", "emphasis", "rule"):
        assert word in text, word


def test_skill_adopts_a_rule_only_on_a_yes_after_rule_test():
    text = skill()
    assert re.search(r"only (on|with|after)[^.\n]*yes|yes[^.\n]*only|never adopt[^.\n]*without", text, re.IGNORECASE)
    assert re.search(r"--example", text)


def test_skill_never_edits_the_working_file_by_hand():
    assert re.search(r"never (edit|write)[^.\n]*working file|only (through|with)[^.\n]*review apply", skill(), re.I)
    assert re.search(r"owner=\"human\"|human-owned|owner is human", skill(), re.I)


def test_agent_states_input_output_and_what_it_never_does():
    text = agent()
    for heading in ("Input", "Output", "Never"):
        assert re.search(rf"^#+ .*{heading}", text, re.MULTILINE | re.IGNORECASE), heading
    assert re.search(r"never[^.\n]*(write|edit)[^.\n]*(working file|file)", text, re.IGNORECASE)


def test_agent_fills_proposed_action_and_one_sentence():
    text = agent()
    for word in ("proposed", "action", "apply", "redraft", "restructure"):
        assert word in text, word
    assert re.search(r"one sentence", text, re.IGNORECASE)
    assert re.search(r"lasting preference", text, re.IGNORECASE)
    assert re.search(r"flag", text, re.IGNORECASE)


def test_the_chain_the_skill_describes_runs_on_a_fixture(tmp_path):
    (tmp_path / "report.md").write_text(SOURCE, encoding="utf-8")
    working = tmp_path / "report.md"
    assert run("build", str(working), cwd=tmp_path).returncode == 0
    version = tmp_path / "report.versions" / "v1"
    clean = tmp_path / "none.json"
    clean.write_text("[]")
    assert run("look", str(version), "--findings", str(clean), cwd=tmp_path).returncode == 0

    from docx import Document

    copy = tmp_path / "report-reviewed.docx"
    shutil.copyfile(version / "report.docx", copy)
    document = Document(str(copy))
    run_ = next(r for p in document.paragraphs for r in p.runs if "Beta holds" in r.text)
    document.add_comment(run_, text="Say 'second paragraph' as 'second part'.", author="Reviewer")
    document.save(str(copy))

    read = run("review", "read", str(copy), cwd=tmp_path)
    assert read.returncode == 0, read.stderr
    plan_path = Path([ln.split()[-1] for ln in read.stdout.splitlines() if ln.strip().endswith(".json")][-1])
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    item = plan["sections"]["beta01"]["confirm"][0]
    item.update(
        accepted=True,
        action="apply",
        proposal="Beta holds the second part of the note.",
    )
    decided = tmp_path / "decided.json"
    decided.write_text(json.dumps(plan), encoding="utf-8")
    applied = run("review", "apply", str(working), "--plan", str(decided), cwd=tmp_path)
    assert applied.returncode == 0, applied.stderr + applied.stdout
    assert "second part" in working.read_text(encoding="utf-8")
    assert run("build", str(working), cwd=tmp_path).returncode == 0
    assert (tmp_path / "report.versions" / "v2").is_dir()


@pytest.mark.parametrize("command", ["review read", "review apply", "rule test"])
def test_each_command_is_named_with_its_flags(command):
    assert f"ai-docs-kit {command}" in skill()
