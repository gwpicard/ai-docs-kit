import json
import re
import shutil
from pathlib import Path

import pytest
from tests.support.fixtures import fixture_path

from ai_docs_kit.cli import main
from ai_docs_kit.model import Finding

DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    folder = tmp_path_factory.mktemp("built")
    shutil.copyfile(fixture_path("doc", "report.md"), folder / "report.md")
    assert main(["build", str(folder / "report.md")]) == 0
    return folder


@pytest.fixture
def work(built, tmp_path) -> Path:
    shutil.copytree(built, tmp_path / "w")
    return tmp_path / "w"


def _version(work: Path) -> Path:
    return work / "report.versions" / "v1"


def _manifest(work: Path) -> dict:
    return json.loads((_version(work) / "manifest.json").read_text())


def _pages(work: Path) -> list[dict]:
    return json.loads((_version(work) / "pages" / "pages.json").read_text())["pages"]


def _finding(work: Path, severity="warning", page=1, section=None, **extra) -> dict:
    section = section or _pages(work)[page - 1]["sections"][0]
    return {
        "severity": severity,
        "rule": "look.crowded",
        "page": page,
        "section": section,
        "message": "The heading sits too close to the figure.",
    } | extra


def _look(work: Path, findings, capsys) -> tuple[int, str, str]:
    file = work / "findings.json"
    file.write_text(json.dumps(findings))
    code = main(["look", str(_version(work)), "--findings", str(file)])
    out = capsys.readouterr()
    return code, out.out, out.err


def test_valid_findings_are_added_to_the_look_record(work, capsys):
    before = (_version(work) / "manifest.json").read_text()
    code, _, _ = _look(work, [_finding(work)], capsys)
    assert code == 0
    after = (_version(work) / "manifest.json").read_text()
    assert after != before
    assert "The heading sits too close to the figure." in after
    assert "look.crowded" in json.dumps(_manifest(work)["look"])


def test_an_empty_findings_file_is_accepted(work, capsys):
    code, _, _ = _look(work, [], capsys)
    assert code == 0


def test_section_not_on_that_page_is_refused_with_a_line(work, capsys):
    pages = _pages(work)
    elsewhere = next(s for s in pages[-1]["sections"] if s not in pages[0]["sections"])
    before = (_version(work) / "manifest.json").read_text()
    code, out, err = _look(work, [_finding(work, page=1, section=elsewhere)], capsys)
    assert code == 2
    assert elsewhere in out + err
    assert (_version(work) / "manifest.json").read_text() == before


def test_unknown_severity_is_refused(work, capsys):
    code, out, err = _look(work, [_finding(work, severity="fatal")], capsys)
    assert code == 2
    assert "fatal" in out + err


@pytest.mark.parametrize("page", [0, 99])
def test_page_out_of_range_is_refused(work, capsys, page):
    section = _pages(work)[0]["sections"][0]
    code, out, err = _look(work, [_finding(work, page=page, section=section)], capsys)
    assert code == 2
    assert str(page) in out + err


def test_each_problem_gets_its_own_line(work, capsys):
    section = _pages(work)[0]["sections"][0]
    bad = [_finding(work, severity="fatal"), _finding(work, page=99, section=section)]
    code, out, err = _look(work, bad, capsys)
    assert code == 2
    assert len((out + err).strip().splitlines()) >= 2


def test_pages_prints_pages_sections_and_engine_findings(work, capsys):
    assert main(["look", str(_version(work)), "--pages"]) == 0
    out = capsys.readouterr().out
    for entry in _pages(work):
        for section in entry["sections"]:
            assert section in out


def test_pages_lists_the_engines_findings(work, capsys):
    path = _version(work) / "findings.json"
    sample = Finding(
        id="f1",
        rule_id="seeded.rule-name",
        tier="geometry",
        severity="warning",
        format="doc",
        section_id="bb002",
        page=1,
        message="Seeded engine finding text.",
        fingerprint="fp",
        remedy={"class": "report", "hint": "Report it."},
    )
    path.write_text(json.dumps([json.loads(sample.model_dump_json())]))
    assert main(["look", str(_version(work)), "--pages"]) == 0
    out = capsys.readouterr().out
    assert "seeded.rule-name" in out


def _sent(work: Path, *extra: str) -> int:
    return main(["sent", str(_version(work)), "--to", "Reviewer One", *extra])


def test_sent_is_refused_until_a_look_entry_exists(work, capsys):
    assert _sent(work) != 0
    assert _manifest(work)["state"] != "sent"
    assert _look(work, [], capsys)[0] == 0
    assert _sent(work) == 0
    assert _manifest(work)["state"] == "sent"


def test_sent_records_the_reviewer_and_the_date(work, capsys):
    _look(work, [], capsys)
    before = len(DATE.findall((_version(work) / "manifest.json").read_text()))
    assert _sent(work) == 0
    text = (_version(work) / "manifest.json").read_text()
    assert "Reviewer One" in text
    assert len(DATE.findall(text)) > before


def test_sent_is_refused_while_the_look_record_has_an_error(work, capsys):
    assert _look(work, [_finding(work, severity="error")], capsys)[0] == 0
    capsys.readouterr()
    assert _sent(work) != 0
    assert _manifest(work)["state"] != "sent"


def test_a_warning_does_not_block_sent(work, capsys):
    _look(work, [_finding(work, severity="warning")], capsys)
    assert _sent(work) == 0


def test_force_with_a_reason_overrides_and_records_it(work, capsys):
    _look(work, [_finding(work, severity="error")], capsys)
    assert _sent(work, "--force", "--reason", "Client asked for it as is") == 0
    manifest = _manifest(work)
    assert manifest["state"] == "sent"
    assert manifest["forced_reason"] == "Client asked for it as is"


def test_force_without_a_reason_is_refused(work, capsys):
    _look(work, [_finding(work, severity="error")], capsys)
    assert _sent(work, "--force") != 0
    assert _manifest(work)["state"] != "sent"


def test_latest_prints_the_latest_sent_version_or_nothing(work, capsys):
    file = work / "report.md"
    capsys.readouterr()
    assert main(["sent", "--latest", str(file)]) == 0
    assert capsys.readouterr().out.strip() == ""
    _look(work, [], capsys)
    assert _sent(work) == 0
    capsys.readouterr()
    assert main(["sent", "--latest", str(file)]) == 0
    assert Path(capsys.readouterr().out.strip().splitlines()[-1]).name == "v1"
