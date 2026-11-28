"""Issue 390: builds locate capacity findings and replace the latest findings file."""

import json
import re

import pytest

from ai_docs_kit.cli import main


def _block(section_id, text):
    return f'::: {{#{section_id} .section intent="bullets"}}\n## Findings\n\n- {text} [S1]\n:::\n'


@pytest.mark.parametrize("target_page", [2, 3])
def test_build_records_the_capacity_findings_actual_page_and_look_prints_it(tmp_path, capsys, target_page):
    sections = [_block("first", "Record the evidence."), _block("last", "Agree the next step.")]
    long_item = "Record the evidence carefully. " * 6
    sections.insert(target_page - 1, _block("a7c31", long_item.strip()))
    working = tmp_path / "deck.md"
    working.write_text(
        "---\ndoctype: pitch-deck\nformat: slides\n---\n\n## Sources\n\n"
        "- [S1] Illustrative workshop notes.\n\n" + "\n".join(sections),
        encoding="utf-8",
    )
    assert main(["build", str(working)]) == 0
    capsys.readouterr()
    version = tmp_path / "deck.versions" / "v1"
    index = json.loads((version / "pages" / "pages.json").read_text())
    assert [page["page"] for page in index["pages"] if "a7c31" in page["sections"]] == [target_page]
    findings = json.loads((version / "findings.json").read_text())
    capacity = [f for f in findings if f["rule_id"] == "source.capacity"]
    assert len(capacity) == 1
    assert capacity[0]["measured"] == {"measure": "item_chars", "value": len(long_item.strip()), "max": 140}
    assert capacity[0]["section_id"] == "a7c31"
    assert main(["look", str(version), "--pages"]) == 0
    output = capsys.readouterr().out
    line = next(line for line in output.splitlines() if line.startswith("- source.capacity "))
    assert capacity[0]["page"] == target_page, "source findings acquire their page from the built section marks"
    assert re.search(rf"\bpage {target_page}\b", line), line
    assert "page None" not in output


@pytest.mark.parametrize("page_key", ["missing", "null"])
def test_look_pages_names_the_section_when_an_older_finding_has_no_page(tmp_path, capsys, page_key):
    # Author a minimal older version, rather than patching generated build outputs.
    version = tmp_path / "deck.versions" / "v1"
    (version / "pages").mkdir(parents=True)
    (version / "pages" / "pages.json").write_text(
        json.dumps(
            {
                "pages": [{"page": 1, "sections": ["a7c31"]}],
            }
        ),
        encoding="utf-8",
    )
    finding = {
        "rule_id": "source.capacity",
        "severity": "warning",
        "section_id": "a7c31",
        "message": "item_chars value 180 exceeds maximum 140 for component bullets",
    }
    if page_key == "null":
        finding["page"] = None
    (version / "findings.json").write_text(json.dumps([finding]), encoding="utf-8")

    assert main(["look", str(version), "--pages"]) == 0
    output = capsys.readouterr().out
    line = next(line for line in output.splitlines() if line.startswith("- source.capacity warning "))
    assert "section a7c31" in line
    assert "page " not in line, "a finding without a page must use its section as the location"
    assert "page None" not in output


@pytest.mark.parametrize("fmt", ["doc", "slides"])
@pytest.mark.parametrize("seed_command", ["check", "build"])
def test_every_build_replaces_the_latest_findings_after_dirty_and_clean_runs(tmp_path, capsys, fmt, seed_command):
    working = tmp_path / "readout.md"
    doctype = "report" if fmt == "doc" else "pitch-deck"
    sections = [_block("target", "unlock practical progress"), _block("other", "Record the evidence.")]
    if fmt == "doc":
        sections.reverse()
    dirty = (
        f"---\ndoctype: {doctype}\nformat: {fmt}\n---\n\n## Sources\n\n"
        "- [S1] Illustrative workshop notes.\n\n" + "\n".join(sections)
    )
    clean = dirty.replace("unlock practical progress", "Record practical progress.")
    working.write_text(dirty, encoding="utf-8")
    assert main([seed_command, str(working)]) == (1 if seed_command == "check" else 0)
    capsys.readouterr()
    report = tmp_path / "build" / "readout.findings.json"
    assert report.is_file(), "a build creates the latest findings file even without an earlier check"
    assert any(f["rule_id"] == "source.banned-terms" for f in json.loads(report.read_text()))

    version_number = 1 if seed_command == "check" else 2
    for text, expect_banned in [(clean, False), (dirty, True), (clean, False)]:
        working.write_text(text, encoding="utf-8")
        assert main(["build", str(working)]) == 0
        capsys.readouterr()
        latest = json.loads(report.read_text())
        version = tmp_path / "readout.versions" / f"v{version_number}" / "findings.json"
        built = json.loads(version.read_text())
        assert any(f["rule_id"] == "source.banned-terms" for f in built) is expect_banned
        assert latest == built, "the adjacent findings file must contain exactly this build's serialised findings"
        if not expect_banned:
            assert latest == [], "a clean build clears every stale finding"
        version_number += 1
