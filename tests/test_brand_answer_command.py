import re
import subprocess
import sys
from pathlib import Path

import yaml

from ai_docs_kit.brand.git import run_git
from ai_docs_kit.brand.questions import BrandQuestion, add_questions, load_questions, open_questions
from judge.test_b_10a_brand_answers import _brand, _files, _rule

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "brand" / "SKILL.md"
MARGIN = "conflict.pages.doc.margin.top"


def run(tmp_path, *args):
    return subprocess.run(
        [sys.executable, "-m", "ai_docs_kit.cli", "brand", "answer", "acme", *args, "--root", str(tmp_path / ".brand")],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )


def snapshot(brand):
    return (_files(brand / "theme"), run_git(brand, "rev-list", "--count", "main"), run_git(brand, "branch", "--list"))


def assert_refused(tmp_path, brand, *args):
    before = snapshot(brand)
    done = run(tmp_path, *args)
    assert done.returncode == 2, done.stderr
    assert len([line for line in (done.stdout + done.stderr).splitlines() if line.strip()]) == 1
    assert snapshot(brand) == before


def test_option_answer_exits_zero_and_closes_the_question(tmp_path):
    brand = _brand(tmp_path)
    done = run(tmp_path, MARGIN, "--option", "b", "--person", "sam")
    assert done.returncode == 0, done.stderr
    question = next(q for q in load_questions(brand) if q.id == MARGIN)
    assert question.option == "b"
    assert question.answered_by == "sam"
    assert question.answer == "18 mm (examples)"
    assert MARGIN not in {q.id for q in open_questions(brand)}
    tokens = yaml.safe_load((brand / "theme/tokens.yaml").read_text())
    assert tokens["pages"]["doc"]["margin"]["top"] == "18mm"


def test_text_answer_closes_the_question(tmp_path):
    brand = _brand(tmp_path)
    done = run(tmp_path, "gap.no-logo", "--text", "No, use the wordmark")
    assert done.returncode == 0, done.stderr
    question = next(q for q in load_questions(brand) if q.id == "gap.no-logo")
    assert question.answer == "No, use the wordmark"
    assert question.answered_by == "owner"
    assert "gap.no-logo" not in {q.id for q in open_questions(brand)}


def test_unknown_question_is_refused(tmp_path):
    assert_refused(tmp_path, _brand(tmp_path), "no.such.question", "--text", "x")


def test_unknown_option_is_refused(tmp_path):
    assert_refused(tmp_path, _brand(tmp_path), MARGIN, "--option", "zzz")


def test_option_and_text_together_are_refused(tmp_path):
    assert_refused(tmp_path, _brand(tmp_path), MARGIN, "--option", "a", "--text", "x")


def test_answer_that_invalidates_the_theme_is_refused(tmp_path):
    brand = _brand(tmp_path)
    bad = BrandQuestion.model_validate(
        {
            "id": "invalid.rule",
            "kind": "rule",
            "text": "Use rule?",
            "options": [
                {"id": "yes", "label": "Yes", "effects": [{"kind": "write-rule", "rule": _rule("no-such-kind")}]}
            ],
        }
    )
    add_questions(brand, [bad])
    run_git(brand, "add", "-A")
    run_git(brand, "commit", "-m", "Add invalid rule question")
    assert_refused(tmp_path, brand, "invalid.rule", "--option", "yes")


def test_skill_names_the_answer_command_where_it_asks_for_confirmation():
    text = SKILL.read_text(encoding="utf-8")
    assert "ai-docs-kit brand answer" in text
    line = next(line for line in text.splitlines() if "ai-docs-kit brand answer" in line)
    assert re.search(r"confirm", line, re.I)
