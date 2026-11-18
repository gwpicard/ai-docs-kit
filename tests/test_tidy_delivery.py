"""Issue 48: tidy the delivery code found by the 17 November pass."""

import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from tests.support.fixtures import fixture_path

from ai_docs_kit.cli import main
from ai_docs_kit.store import VersionImmutable, update_manifest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture
def version(tmp_path) -> Path:
    shutil.copyfile(fixture_path("doc", "report.md"), tmp_path / "report.md")
    assert main(["build", str(tmp_path / "report.md")]) == 0
    return tmp_path / "report.versions" / "v1"


def test_wrong_typed_look_names_the_field_and_type(version):
    with pytest.raises(VersionImmutable) as caught:
        update_manifest(version, look={"clean": True})
    message = str(caught.value)
    assert "look" in message
    assert "dict" in message
    assert "Only delivery fields may change" not in message


def _run_cleanup(tmp_path: Path, body: str) -> subprocess.CompletedProcess[str]:
    """Run an inner test under the tests/conftest.py plugin and its session clean-up."""
    inner = tmp_path / "test_inner.py"
    inner.write_text(f"from pathlib import Path\nFIXTURES = Path({str(FIXTURES)!r})\ndef test_inner():\n{body}\n")
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    command = [sys.executable, "-m", "pytest", str(inner), "-q", "-c", os.devnull]
    command += ["-p", "no:cacheprovider", "-p", "tests.conftest"]
    return subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True)


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="needs permissions to be enforced")
def test_cleanup_reports_a_path_it_cannot_remove(tmp_path):
    name = f"_locked_{uuid.uuid4().hex}"
    locked = FIXTURES / name
    try:
        result = _run_cleanup(
            tmp_path,
            f"    d = FIXTURES / {name!r}\n    d.mkdir()\n    (d / 'sub').mkdir()\n    d.chmod(0o555)\n",
        )
    finally:
        if locked.exists():
            locked.chmod(0o755)
            shutil.rmtree(locked)
    assert result.returncode != 0, result.stdout + result.stderr
    assert name in result.stdout + result.stderr


def test_cleanup_removes_a_created_folder_without_error(tmp_path):
    name = f"_made_{uuid.uuid4().hex}"
    try:
        result = _run_cleanup(
            tmp_path,
            f"    d = FIXTURES / {name!r} / 'a'\n    d.mkdir(parents=True)\n    (d / 'f.txt').write_text('x')\n",
        )
        left = (FIXTURES / name).exists()
    finally:
        shutil.rmtree(FIXTURES / name, ignore_errors=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not left


def test_duplicate_brand_skill_tests_are_gone():
    tests = ROOT / "tests"
    assert not (tests / "test_brand_skill_build_exit.py").exists()
    assert not (tests / "test_brand_skill_accepts_only_exit_zero.py").exists()
    assert "returncode == 0" in (tests / "test_brand_skill.py").read_text()
    needle = "from test_brand" + "_skill"
    hits = [p.name for p in tests.rglob("*.py") if needle in p.read_text()]
    assert hits == []


def test_plan_lessons_hold_the_four_new_lines():
    text = (ROOT / "PLAN.md").read_text()
    lessons = re.search(r"^## Lessons\n(.*?)(?=^## )", text, re.S | re.M).group(1)
    lines = [line for line in lessons.splitlines() if line.strip()]
    assert len(lines) < 30
    for needle in ("tmp_path", "caller", "run-twice", "exit 2"):
        assert any(needle in line for line in lines), needle
