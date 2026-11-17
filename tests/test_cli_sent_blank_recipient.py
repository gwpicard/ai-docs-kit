import json
import shutil

from tests.support.fixtures import fixture_path

from ai_docs_kit.cli import main


def test_sent_refuses_a_blank_recipient(tmp_path):
    shutil.copyfile(fixture_path("doc", "report.md"), tmp_path / "report.md")
    assert main(["build", str(tmp_path / "report.md")]) == 0
    version = tmp_path / "report.versions" / "v1"
    file = tmp_path / "findings.json"
    file.write_text(json.dumps([]))
    assert main(["look", str(version), "--findings", str(file)]) == 0
    assert main(["sent", str(version), "--to", "  "]) == 2
    assert json.loads((version / "manifest.json").read_text())["state"] != "sent"
