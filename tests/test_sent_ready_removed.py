import json
import shutil
from pathlib import Path

import pytest
from tests.support.fixtures import fixture_path

from ai_docs_kit.cli import main

REMOVED_KEYS = ("state", "sent_to", "sent_on", "forced_reason")
SCHEMA = Path(__file__).parent.parent / "docs" / "schemas" / "store" / "Manifest.schema.json"


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    folder = tmp_path_factory.mktemp("built")
    shutil.copyfile(fixture_path("doc", "report.md"), folder / "report.md")
    assert main(["build", str(folder / "report.md")]) == 0
    return folder


@pytest.fixture
def version(built, tmp_path) -> Path:
    shutil.copytree(built, tmp_path / "w")
    return tmp_path / "w" / "report.versions" / "v1"


def _manifest(version: Path) -> dict:
    return json.loads((version / "manifest.json").read_text())


def _edit(version: Path, change) -> None:
    data = _manifest(version)
    change(data)
    (version / "manifest.json").write_text(json.dumps(data))


def _summary(version: Path, findings: list[dict], capsys) -> str:
    file = version.parent / "findings.json"
    file.write_text(json.dumps(findings))
    capsys.readouterr()
    assert main(["look", str(version), "--findings", str(file)]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    return lines[-1]


@pytest.mark.parametrize("command", ["sent", "ready"])
def test_the_removed_commands_are_unknown_with_exit_2(version, command, capsys):
    with pytest.raises(SystemExit) as stop:
        main([command, str(version), "--to", "Reviewer One"])
    assert stop.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_help_lists_neither_command(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    words = capsys.readouterr().out.replace(",", " ").replace("{", " ").replace("}", " ").split()
    assert "sent" not in words
    assert "ready" not in words


@pytest.mark.parametrize("state", ["draft", "ready", "sent"])
def test_a_manifest_with_the_old_state_keys_still_loads(version, state, capsys):
    def old(data: dict) -> None:
        data.update(state=state, sent_to=["Reviewer One"], sent_on=["2026-01-02"], forced_reason="late")

    _edit(version, old)
    capsys.readouterr()
    assert main(["look", str(version), "--pages"]) == 0
    from ai_docs_kit.store import load_version

    loaded = load_version(version)
    assert not any(key in type(loaded.manifest).model_fields for key in REMOVED_KEYS)
    assert not any(hasattr(loaded.manifest, key) for key in REMOVED_KEYS)


def test_a_new_manifest_does_not_write_the_old_keys(version):
    assert not any(key in _manifest(version) for key in REMOVED_KEYS)


def test_the_manifest_schema_drops_the_old_keys():
    properties = json.loads(SCHEMA.read_text())["properties"]
    assert not any(key in properties for key in REMOVED_KEYS)


def test_the_gate_functions_are_gone_and_ship_gate_stays():
    from ai_docs_kit.store import gate

    for name in ("sent_gate", "mark_sent", "mark_ready", "check_force_reason"):
        assert not hasattr(gate, name)
    assert callable(gate.ship_gate)


def test_look_findings_ends_with_the_summary_line_for_a_clean_look(version, capsys):
    errors = _manifest(version)["findings"]["error"]
    assert _summary(version, [], capsys) == f"open errors: {errors}, pages not looked at: none"


def test_the_summary_counts_a_recorded_look_error(version, capsys):
    errors = _manifest(version)["findings"]["error"]
    section = json.loads((version / "pages" / "pages.json").read_text())["pages"][0]["sections"][0]
    finding = {"severity": "error", "rule": "look.cut-off", "page": 1, "section": section, "message": "Cut off."}
    assert _summary(version, [finding], capsys) == f"open errors: {errors + 1}, pages not looked at: none"


def test_the_summary_names_the_pages_not_looked_at(version, capsys):
    _edit(version, lambda d: d["look"].update(could_not=["semantic page 2: timeout"], clean=False))
    line = _summary(version, [], capsys)
    assert line.startswith("open errors: ")
    assert "pages not looked at: " in line
    assert "page 2" in line
    assert not line.endswith("none")
