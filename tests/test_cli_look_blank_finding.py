import json
import shutil
from pathlib import Path

import pytest
from tests.support.fixtures import fixture_path

from ai_docs_kit.cli import main


@pytest.fixture
def version(tmp_path) -> Path:
    shutil.copyfile(fixture_path("doc", "report.md"), tmp_path / "report.md")
    assert main(["build", str(tmp_path / "report.md")]) == 0
    return tmp_path / "report.versions" / "v1"


def _finding(version: Path, **extra) -> dict:
    section = json.loads((version / "pages" / "pages.json").read_text())["pages"][0]["sections"][0]
    return {
        "severity": "warning",
        "rule": "look.crowded",
        "page": 1,
        "section": section,
        "message": "Too tight.",
    } | extra


@pytest.mark.parametrize("field", ["rule", "message"])
def test_a_finding_with_a_blank_rule_or_message_is_refused(version, tmp_path, capsys, field):
    file = tmp_path / "findings.json"
    file.write_text(json.dumps([_finding(version, **{field: "  "})]))
    assert main(["look", str(version), "--findings", str(file)]) == 2, capsys.readouterr().out
    assert json.loads((version / "manifest.json").read_text())["look"]["agent"] is None


def test_recording_the_same_findings_twice_does_not_duplicate_them(version, tmp_path):
    file = tmp_path / "findings.json"
    file.write_text(json.dumps([_finding(version)]))
    assert main(["look", str(version), "--findings", str(file)]) == 0
    assert main(["look", str(version), "--findings", str(file)]) == 0
    agent = json.loads((version / "manifest.json").read_text())["look"]["agent"]
    assert len(agent) == 1
