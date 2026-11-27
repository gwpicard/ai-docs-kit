"""Additional issue 390 cases through the commands a writer runs."""

import json
import re
from pathlib import Path

import pytest

from ai_docs_kit.cli import main


def _section(section_id, text, intent="bullets"):
    return f'::: {{#{section_id} .section intent="{intent}"}}\n## Findings\n\n{text}\n:::\n'


def _working(folder, sections, fmt="doc", source="Illustrative workshop notes."):
    working = folder / "readout.md"
    working.write_text(
        f"---\nformat: {fmt}\n---\n\n## Sources\n\n- [S1] {source}\n\n" + "\n".join(sections),
        encoding="utf-8",
    )
    return working


@pytest.mark.parametrize("quotes", [('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’")])
@pytest.mark.parametrize("evidence", ["source-list", "gathered-facts"])
def test_source_quotation_with_an_internal_contraction_keeps_its_banned_term(tmp_path, capsys, quotes, evidence):
    opening, closing = quotes
    words = "we don't know whether to unlock this gate"
    quotation = f"{opening}{words}{closing}"
    sections = [
        _section("verified", f"- The recording says {quotation}. [S1]"),
        _section("unquoted", f"- The recording says {words}. [S1]"),
        _section("invented", f"- The recording says {opening}unlock another gate{closing}. [S1]"),
        _section("mixed", f"- The recording says {quotation}; we unlock another gate. [S1]"),
    ]
    source = f"The recorded words were {words}."
    if evidence == "gathered-facts":
        (tmp_path / "workshop.md").write_text(source, encoding="utf-8")
        sections.reverse()
    working = _working(tmp_path, sections, source="workshop.md" if evidence == "gathered-facts" else source)
    if evidence == "gathered-facts":
        incoming = tmp_path / "facts.json"
        incoming.write_text(json.dumps([{"source": "S1", "text": source}]), encoding="utf-8")
        assert main(["facts", "add", str(working), str(incoming)]) == 0
        assert capsys.readouterr().err == ""

    assert main(["check", str(working)]) == 1
    assert capsys.readouterr().err == ""
    findings = json.loads((tmp_path / "build" / "readout.findings.json").read_bytes())
    banned = [finding for finding in findings if finding["rule_id"] == "source.banned-terms"]
    assert {finding["section_id"] for finding in banned} == {"unquoted", "invented", "mixed"}, (
        "apostrophes inside a verified source quotation must not end its exemption"
    )
    assert all(finding["measured"] == {"field": "items", "terms": ["unlock"]} for finding in banned)


@pytest.mark.parametrize("reverse", [False, True], ids=["target-second", "target-third"])
def test_document_capacity_page_comes_from_layout_instead_of_section_position(tmp_path, capsys, reverse):
    others = [_section("first", "- Record the evidence."), _section("other", "- Agree the next step.")]
    working = _working(tmp_path, others)
    for version_number, length in enumerate([240, 241], start=1):
        text = ("record the evidence carefully " * 10)[:length]
        sections = [*others]
        sections.insert(2 if reverse else 1, _section("a7c31", f"- {text}"))
        _working(tmp_path, sections)
        assert main(["build", str(working)]) == 0
        captured = capsys.readouterr()
        assert captured.err == ""
        version = tmp_path / "readout.versions" / f"v{version_number}"
        pages = json.loads((version / "pages" / "pages.json").read_bytes())["pages"]
        assert len(pages) == 1
        assert set(pages[0]["sections"]) == {"first", "other", "a7c31"}
        findings = json.loads((version / "findings.json").read_bytes())
        capacity = [finding for finding in findings if finding["rule_id"] == "source.capacity"]
        assert main(["look", str(version), "--pages"]) == 0
        listing = capsys.readouterr().out
        if length == 240:
            assert capacity == []
            assert "source.capacity" not in listing
        else:
            assert len(capacity) == 1
            assert capacity[0]["section_id"] == "a7c31"
            assert capacity[0]["measured"] == {"measure": "item_chars", "value": 241, "max": 240}
            assert capacity[0]["page"] == pages[0]["page"], "flowing sections share their rendered page"
            line = next(line for line in listing.splitlines() if line.startswith("- source.capacity "))
            assert "page 1" in line and "page None" not in listing


@pytest.mark.parametrize("fmt", ["doc", "slides"])
def test_json_build_refreshes_findings_after_an_error_and_on_later_builds(tmp_path, capsys, fmt):
    working = _working(tmp_path, [_section("a7c31", "- unlock practical progress.")], fmt=fmt)
    dirty = working.read_text(encoding="utf-8")
    clean = dirty.replace("unlock", "record")
    assert main(["check", str(working)]) == 1
    assert capsys.readouterr().err == ""
    report = tmp_path / "build" / "readout.findings.json"
    assert any(finding["rule_id"] == "source.banned-terms" for finding in json.loads(report.read_bytes()))

    for version_number, text in enumerate([clean, dirty, clean], start=1):
        working.write_text(text, encoding="utf-8")
        assert main(["build", str(working), "--json"]) == 0
        captured = capsys.readouterr()
        assert captured.err == ""
        result = json.loads(captured.out)
        version = tmp_path / "readout.versions" / f"v{version_number}"
        assert Path(result["version"]) == version
        stored = json.loads((version / "findings.json").read_bytes())
        assert result["findings"] == stored
        assert any(finding["rule_id"] == "source.banned-terms" for finding in stored) is (text == dirty)
        assert json.loads(report.read_bytes()) == stored, "JSON builds must replace the adjacent findings file too"
        if text == clean:
            assert stored == []


@pytest.mark.parametrize("count, component, maximum", [(2, "cards", 100), (5, "bullets", 140)])
def test_section_put_warns_against_the_new_blocks_chosen_component(tmp_path, capsys, count, component, maximum):
    # The old block chooses bullets; replacing it may choose cards instead.
    working = _working(
        tmp_path,
        [_section("a7c31", "- Original evidence.", "card-set"), _section("other", "- Keep this separate.")],
        fmt="slides",
    )
    block = tmp_path / "block.md"
    for length in [maximum, maximum + 1]:
        body = "x" * length
        block.write_text(_section("a7c31", "\n".join([f"- {body}"] * count), "card-set"), encoding="utf-8")
        assert main(["section", "put", str(working), "a7c31", "--from", str(block)]) == 0
        captured = capsys.readouterr()
        assert main(["section", "get", str(working), "a7c31"]) == 0
        assert capsys.readouterr().out.count(body) == count
        assert "Keep this separate." in working.read_text(encoding="utf-8")
        assert main(["section", "brief", str(working), "a7c31", "--json"]) == 0
        brief = json.loads(capsys.readouterr().out)
        assert brief["component"] == component
        assert brief["capacity"]["item_chars"][1] == maximum
        warnings = [
            line for line in (captured.out + captured.err).splitlines() if line.startswith("warning source.capacity ")
        ]
        if length == maximum:
            assert warnings == []
        else:
            assert len(warnings) == 1, "warn once for the exceeded item_chars measure and still save the block"
            assert "item_chars" in warnings[0]
            assert re.search(rf"\b{maximum + 1}\b", warnings[0])
            assert re.search(rf"\b{maximum}\b", warnings[0])
