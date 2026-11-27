"""Judge issue 390 through the writer's commands, with readable source fixtures."""

import json
import re
from pathlib import Path

import pytest

from ai_docs_kit.cli import main

ROOT = Path(__file__).resolve().parents[1]


def _block(section_id, body, title="Findings"):
    return f'::: {{#{section_id} .section intent="bullets"}}\n## {title}\n\n{body}\n:::\n'


def _working(tmp_path, sections, fmt="slides", sources=None):
    working = tmp_path / "readout.md"
    doctype = "report" if fmt == "doc" else "pitch-deck"
    working.write_text(
        f"---\ndoctype: {doctype}\nformat: {fmt}\n---\n\n## Sources\n\n"
        + "\n".join(sources or ["- [S1] Illustrative workshop notes."])
        + "\n\n"
        + "\n".join(sections),
        encoding="utf-8",
    )
    return working


@pytest.mark.parametrize("command", ["check", "build"])
@pytest.mark.parametrize("evidence", ["source-list", "gathered-facts"])
@pytest.mark.parametrize("quotes", [('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’")])
def test_banned_terms_exempt_only_occurrences_quoted_from_evidence(tmp_path, capsys, command, evidence, quotes):
    opening, closing = quotes
    quotation = f"{opening}unlock practical progress{closing}"
    unsupported = f"{opening}unlock a hidden switch{closing}"
    source_text = "The workshop recorded a request to unlock practical progress for everyone."
    sections = [
        _block(
            "quoted",
            f"The source says {quotation}. [S2]\n\n"
            f"- **{quotation}** {quotation} [S2]\n  - {quotation}\n\n> spoken: {quotation}",
            title=quotation,
        ),
        _block("raw", "- unlock practical progress [S2]"),
        _block("unsupported", f"- {unsupported} [S2]"),
        _block("mixed", f"The source says {quotation}; we also unlock practical progress. [S2]"),
    ]
    sources = ["- [S1] Separate workshop notes.", "- [S2] " + source_text]
    if evidence == "gathered-facts":
        # facts add validates local sources before storing even facts without figures.
        (tmp_path / "separate.md").write_text("The recording is complete.\n", encoding="utf-8")
        (tmp_path / "workshop.md").write_text(source_text + "\n", encoding="utf-8")
        sources = ["- [S1] separate.md", "- [S2] workshop.md"]
        sections.reverse()
        sources.reverse()
    working = _working(tmp_path, sections, sources=sources)
    if evidence == "gathered-facts":
        incoming = tmp_path / "gathered.json"
        incoming.write_text(
            json.dumps(
                [
                    {"text": "The recording is complete.", "source": "S1"},
                    {"text": source_text, "source": "S2"},
                ]
            ),
            encoding="utf-8",
        )
        assert main(["facts", "add", str(working), str(incoming)]) == 0
        assert capsys.readouterr().err == ""
        stored = tmp_path / ".ai_docs_kit" / "facts" / "readout.md.json"
        assert any(fact["text"] == source_text for fact in json.loads(stored.read_text(encoding="utf-8")))

    assert main([command, str(working)]) == (1 if command == "check" else 0)
    assert capsys.readouterr().err == ""
    report = (
        tmp_path / "build" / "readout.findings.json"
        if command == "check"
        else tmp_path / "readout.versions" / "v1" / "findings.json"
    )
    findings = [f for f in json.loads(report.read_text(encoding="utf-8")) if f["rule_id"] == "source.banned-terms"]
    assert {(f["section_id"], f["measured"]["field"]) for f in findings} == {
        ("raw", "items"),
        ("unsupported", "items"),
        ("mixed", "paragraphs"),
    }, "preserve verified quotations, but still report unsupported quotes and unquoted occurrences"
    assert all(f["measured"]["terms"] == ["unlock"] for f in findings)


def _assert_quote_guidance(text):
    paragraphs = [" ".join(part.lower().split()) for part in re.split(r"\n\s*\n", text)]
    assert any(
        "source" in part
        and "quot" in part
        and re.search(r"\b(?:keep\w*|retain\w*|preserv\w*)\b", part)
        and ("contraction" in part or "don't know" in part or "don’t know" in part)
        for part in paragraphs
    ), "explain that source quotations keep their own wording, including contractions"


@pytest.mark.parametrize("reverse", [False, True], ids=["target-first", "target-last"])
def test_section_brief_explains_the_exception_to_the_document_voice(tmp_path, capsys, reverse):
    sections = [_block("a7c31", "- Record the evidence."), _block("other", "- Agree the next step.")]
    if reverse:
        sections.reverse()
    working = _working(tmp_path, sections, fmt="doc")
    before = working.read_bytes()
    voice = ROOT / "src" / "ai_docs_kit" / "themes" / "neutral" / "voice" / "terminology.yaml"
    assert "do not use contractions" in voice.read_text(encoding="utf-8")
    assert main(["section", "brief", str(working), "a7c31"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "do not use contractions" in captured.out
    assert working.read_bytes() == before
    _assert_quote_guidance(captured.out)


def test_write_section_explains_how_source_quotations_keep_their_form():
    _assert_quote_guidance((ROOT / "agents" / "write-section.md").read_text(encoding="utf-8"))


@pytest.mark.parametrize("target_page", [2, 3])
def test_build_locates_capacity_findings_from_the_rendered_section(tmp_path, capsys, target_page):
    text = ("Record the evidence carefully. " * 6).strip()
    sections = [_block("first", "- Record the evidence."), _block("last", "- Agree the next step.")]
    sections.insert(target_page - 1, _block("a7c31", f"- {text}"))
    working = _working(tmp_path, sections)
    assert main(["build", str(working)]) == 0
    capsys.readouterr()
    version = tmp_path / "readout.versions" / "v1"
    pages = json.loads((version / "pages" / "pages.json").read_text(encoding="utf-8"))["pages"]
    assert [page["page"] for page in pages if "a7c31" in page["sections"]] == [target_page]
    findings = json.loads((version / "findings.json").read_text(encoding="utf-8"))
    capacity = [f for f in findings if f["rule_id"] == "source.capacity"]
    assert len(capacity) == 1
    assert capacity[0]["section_id"] == "a7c31"
    assert capacity[0]["measured"] == {"measure": "item_chars", "value": len(text), "max": 140}
    assert main(["look", str(version), "--pages"]) == 0
    output = capsys.readouterr().out
    line = next(line for line in output.splitlines() if line.startswith("- source.capacity warning "))
    assert capacity[0]["page"] == target_page, "attach the section's actual page after the layout pass"
    assert re.search(rf"\bpage {target_page}\b", line), line
    assert "page None" not in output


@pytest.mark.parametrize("missing_page", [False, True], ids=["null-page", "absent-page"])
def test_look_pages_uses_the_section_when_a_capacity_finding_has_no_page(tmp_path, capsys, missing_page):
    # Author an older-version fixture rather than patching generated build outputs.
    version = tmp_path / "readout.versions" / "v1"
    (version / "pages").mkdir(parents=True)
    (version / "pages" / "pages.json").write_text(
        json.dumps({"pages": [{"page": 3, "sections": ["a7c31"]}]}), encoding="utf-8"
    )
    finding = {
        "rule_id": "source.capacity",
        "severity": "warning",
        "section_id": "a7c31",
        "message": "item_chars value 180 exceeds maximum 140 for component bullets",
    }
    # Pair the known-page control with the missing-page defect in each invocation.
    for page in [3, None]:
        finding["page"] = page
        if page is None and missing_page:
            del finding["page"]
        (version / "findings.json").write_text(json.dumps([finding]), encoding="utf-8")
        assert main(["look", str(version), "--pages"]) == 0
        captured = capsys.readouterr()
        assert captured.err == ""
        line = next(line for line in captured.out.splitlines() if line.startswith("- source.capacity warning "))
        assert ("section a7c31" if page is None else "page 3") in line
        assert "page None" not in line


@pytest.mark.parametrize("fmt", ["doc", "slides"])
@pytest.mark.parametrize("seed_command", ["check", "build"])
def test_build_replaces_the_adjacent_findings_file_on_every_run(tmp_path, capsys, fmt, seed_command):
    working = _working(tmp_path, [_block("a7c31", "- unlock practical progress [S1]")], fmt=fmt)
    dirty = working.read_text(encoding="utf-8")
    clean = dirty.replace("unlock practical progress", "Record practical progress.")
    assert main([seed_command, str(working)]) == (1 if seed_command == "check" else 0)
    capsys.readouterr()
    report = tmp_path / "build" / "readout.findings.json"
    assert report.is_file(), "build must create its findings file without an earlier check"
    assert any(f["rule_id"] == "source.banned-terms" for f in json.loads(report.read_text(encoding="utf-8")))

    first_version = 1 if seed_command == "check" else 2
    for version_number, text in enumerate([clean, dirty, clean], start=first_version):
        working.write_text(text, encoding="utf-8")
        assert main(["build", str(working)]) == 0
        capsys.readouterr()
        version = tmp_path / "readout.versions" / f"v{version_number}" / "findings.json"
        current = json.loads(version.read_text(encoding="utf-8"))
        assert any(f["rule_id"] == "source.banned-terms" for f in current) is (text == dirty)
        latest = json.loads(report.read_text(encoding="utf-8"))
        assert latest == current, "replace stale findings with this build's serialised findings"
        if text == clean:
            assert latest == []


@pytest.mark.parametrize("fmt, title_max, items_max, chars_max", [("slides", 8, 6, 140), ("doc", 10, 40, 240)])
@pytest.mark.parametrize("reverse", [False, True], ids=["target-first", "target-last"])
def test_section_put_warns_once_per_exceeded_limit_and_still_saves(
    tmp_path, capsys, fmt, title_max, items_max, chars_max, reverse
):
    sections = [_block("a7c31", "- Original evidence."), _block("other", "- Keep this separate.")]
    if reverse:
        sections.reverse()
    working = _working(tmp_path, sections, fmt=fmt)
    replacement = tmp_path / "block.md"
    title = " ".join(["evidence"] * title_max)
    body = "x" * (chars_max - len("evidence"))
    nested = "z" * (chars_max + 20)
    # At the maximum, head plus body fits; nested text does not count towards it.
    control = "\n".join([f"- **evidence** {body}\n  - {nested}"] * items_max)
    replacement.write_text(_block("a7c31", control, title), encoding="utf-8")
    assert main(["section", "put", str(working), "a7c31", "--from", str(replacement)]) == 0
    captured = capsys.readouterr()
    assert "warning source.capacity" not in captured.out + captured.err

    title += " evidence"
    body += "x"
    over_limit = "\n".join([f"- **evidence** {body}\n  - {nested}"] * (items_max + 1))
    replacement.write_text(_block("a7c31", over_limit, title), encoding="utf-8")
    assert main(["section", "put", str(working), "a7c31", "--from", str(replacement)]) == 0
    captured = capsys.readouterr()
    assert main(["section", "get", str(working), "a7c31"]) == 0
    saved = capsys.readouterr().out
    assert title in saved and saved.count(body) == items_max + 1 and saved.count(nested) == items_max + 1
    assert "Keep this separate." in working.read_text(encoding="utf-8")
    warnings = [
        line for line in (captured.out + captured.err).splitlines() if line.startswith("warning source.capacity ")
    ]
    assert len(warnings) == 3, "each exceeded capacity measure warns without refusing the block"
    for measure, maximum in [("title_words", title_max), ("items", items_max), ("item_chars", chars_max)]:
        matches = [line for line in warnings if re.search(rf"\b{measure}\b", line)]
        assert len(matches) == 1, warnings
        assert re.search(rf"\b{maximum + 1}\b", matches[0]) and re.search(rf"\b{maximum}\b", matches[0])
