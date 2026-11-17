import json
import shutil

import pytest
from tests.support.fixtures import fixture_path

from ai_docs_kit.cli import main


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    folder = tmp_path_factory.mktemp("built")
    shutil.copyfile(fixture_path("doc", "report.md"), folder / "report.md")
    assert main(["build", str(folder / "report.md")]) == 0
    return folder


@pytest.mark.parametrize("content", [{}, [], {"pages": 3}, {"pages": [{"page": 1}]}])
def test_look_pages_with_a_malformed_page_index_exits_two(built, tmp_path, capsys, content):
    shutil.copytree(built, tmp_path / "w")
    version = tmp_path / "w" / "report.versions" / "v1"
    (version / "pages" / "pages.json").write_text(json.dumps(content))
    assert main(["look", str(version), "--pages"]) == 2
    assert capsys.readouterr().err


def test_look_pages_with_a_malformed_findings_file_exits_two(built, tmp_path, capsys):
    shutil.copytree(built, tmp_path / "w")
    version = tmp_path / "w" / "report.versions" / "v1"
    (version / "findings.json").write_text('[{"x": 1}]')
    assert main(["look", str(version), "--pages"]) == 2
    assert capsys.readouterr().err
