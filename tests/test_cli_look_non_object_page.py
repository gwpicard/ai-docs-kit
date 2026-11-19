import json
import shutil

import pytest
from tests.support.fixtures import fixture_path

from ai_docs_kit.cli import main


@pytest.mark.parametrize("pages", [[1], ["a"], [None], [[]]])
def test_look_pages_with_a_non_object_page_entry_exits_two(tmp_path, capsys, pages):
    shutil.copyfile(fixture_path("doc", "report.md"), tmp_path / "report.md")
    assert main(["build", str(tmp_path / "report.md")]) == 0
    version = tmp_path / "report.versions" / "v1"
    (version / "pages" / "pages.json").write_text(json.dumps({"pages": pages}))
    assert main(["look", str(version), "--pages"]) == 2
    assert capsys.readouterr().err
