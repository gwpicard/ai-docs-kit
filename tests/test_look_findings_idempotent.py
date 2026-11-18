import json
import shutil
from pathlib import Path

import pytest

from ai_docs_kit.cli import main

DECK = """---
doctype: pitch-deck
format: slides
title: Readout
---

## Sources

- [S1] Illustrative deck content

::: {#cover intent=cover}
## Readout
A short deck for build tests.
:::

::: {#agenda intent=agenda}
## Today's agenda
- Explore the findings
- Sales grew 42% last year
- Discuss next steps [S7]
:::
"""


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    folder = tmp_path_factory.mktemp("built")
    (folder / "mini.md").write_text(DECK, encoding="utf-8")
    assert main(["build", str(folder / "mini.md")]) == 0
    return folder


@pytest.fixture
def version(built, tmp_path) -> Path:
    shutil.copytree(built, tmp_path / "w")
    return tmp_path / "w" / "mini.versions" / "v1"


def _finding(message="The title is cut off.", severity="error", page=1, section="cover", **extra) -> dict:
    return {"severity": severity, "rule": "look.cut-off", "page": page, "section": section, "message": message} | extra


def _run(version: Path, findings, name="findings.json") -> int:
    file = version.parent / name
    file.write_text(json.dumps(findings))
    return main(["look", str(version), "--findings", str(file)])


def _look(version: Path) -> dict:
    return json.loads((version / "manifest.json").read_text())["look"]


def _agent_messages(version: Path) -> list[str]:
    return [f["message"] for f in _look(version)["agent"]]


def test_the_same_file_twice_leaves_the_look_record_as_after_the_first_run(version):
    assert _run(version, [_finding(), _finding("Second.", severity="warning", page=2, section="agenda")]) == 0
    first = _look(version)
    assert _run(version, [_finding(), _finding("Second.", severity="warning", page=2, section="agenda")]) == 0
    assert _look(version) == first
    assert len(first["agent"]) == 2


def test_a_repeated_finding_inside_one_file_is_recorded_once(version):
    assert _run(version, [_finding(), _finding()]) == 0
    assert _agent_messages(version) == ["The title is cut off."]


def test_a_second_file_adds_only_the_findings_not_recorded(version):
    assert _run(version, [_finding("One.")], "a.json") == 0
    assert _run(version, [_finding("One."), _finding("Two.")], "b.json") == 0
    assert _agent_messages(version) == ["One.", "Two."]


@pytest.mark.parametrize(
    "change",
    [{"message": "Other."}, {"severity": "warning"}, {"section": "agenda", "page": 2}, {"section": "agenda"}],
)
def test_a_finding_differing_in_one_key_field_is_added(version, change):
    assert _run(version, [_finding()], "a.json") == 0
    other = _finding(**change)
    if other["section"] == "agenda" and other["page"] == 1:
        other["page"] = 2
        other["message"] = "Differs."  # a section off its page is refused, so vary page too
    assert _run(version, [other], "b.json") == 0
    assert len(_look(version)["agent"]) == 2


@pytest.mark.parametrize("content", [None, "not json", "[1, 2]", "{}", '{"pages": 3}', '{"pages": null}'])
def test_a_damaged_page_index_exits_two_with_one_line_and_no_traceback(version, capsys, content):
    index = version / "pages" / "pages.json"
    if content is None:
        index.unlink()
    else:
        index.write_text(content)
    before = (version / "manifest.json").read_bytes()
    capsys.readouterr()
    assert _run(version, [_finding()]) == 2
    err = capsys.readouterr().err
    assert len(err.strip().splitlines()) == 1
    assert "pages.json" in err
    assert "Traceback" not in err
    assert (version / "manifest.json").read_bytes() == before


def test_look_pages_prints_every_page_section_and_engine_finding_in_order(version, capsys):
    capsys.readouterr()
    assert main(["look", str(version), "--pages"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "page 1: cover",
        "page 2: agenda",
        "engine findings (do not repeat):",
        "- source.unknown-citation warning page None section agenda: S7 is not in the sources.",
        "- source.citations-resolve error page None section agenda: citation key S7 is not listed in ## Sources",
    ]
