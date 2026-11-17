import json
import shutil
from pathlib import Path

import pytest
from tests.support.fixtures import fixture_path

from ai_docs_kit.cli import main


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


def _edit(version: Path, change) -> None:
    path = version / "manifest.json"
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data))


def _state(version: Path) -> str:
    return json.loads((version / "manifest.json").read_text())["state"]


def _looked(version: Path, tmp_path: Path) -> None:
    file = tmp_path / "none.json"
    file.write_text("[]")
    assert main(["look", str(version), "--findings", str(file)]) == 0


def _sent(version: Path, *extra: str) -> int:
    return main(["sent", str(version), "--to", "Reviewer", *extra])


def test_could_not_pages_block_sent(version, tmp_path):
    _looked(version, tmp_path)
    _edit(version, lambda d: d["look"].update(could_not=["page 2"], clean=False))
    assert _sent(version) == 1
    assert _state(version) != "sent"


def test_engine_errors_block_sent(version, tmp_path):
    _looked(version, tmp_path)
    _edit(version, lambda d: (d["findings"].update(error=1), d["look"].update(clean=False)))
    assert _sent(version) == 1
    assert _state(version) != "sent"


def test_unclean_look_blocks_sent(version, tmp_path):
    _looked(version, tmp_path)
    _edit(version, lambda d: d["look"].update(clean=False))
    assert _sent(version) == 1


def test_no_look_record_blocks_sent(version):
    _edit(version, lambda d: d.update(look=None))
    assert _sent(version) == 1


def test_findings_are_refused_without_a_look_record(version, tmp_path):
    _edit(version, lambda d: d.update(look=None))
    file = tmp_path / "none.json"
    file.write_text("[]")
    assert main(["look", str(version), "--findings", str(file)]) == 2
    assert json.loads((version / "manifest.json").read_text())["look"] is None


def test_force_overrides_unlooked_pages(version, tmp_path):
    _looked(version, tmp_path)
    _edit(version, lambda d: d["look"].update(could_not=["page 2"], clean=False))
    assert _sent(version, "--force", "--reason", "agreed") == 0
    assert _state(version) == "sent"


def test_findings_run_twice_append(version, tmp_path):
    page = json.loads((version / "pages" / "pages.json").read_text())["pages"][0]
    item = {"severity": "info", "rule": "r", "page": 1, "section": page["sections"][0], "message": "m"}
    file = tmp_path / "one.json"
    file.write_text(json.dumps([item]))
    for _ in range(2):
        assert main(["look", str(version), "--findings", str(file)]) == 0
    assert len(json.loads((version / "manifest.json").read_text())["look"]["agent"]) == 2
