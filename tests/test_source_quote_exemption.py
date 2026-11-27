"""Issue 390: source quotations keep their wording through the public commands."""

import json
import re
from pathlib import Path

import pytest

from ai_docs_kit.cli import main

ROOT = Path(__file__).resolve().parents[1]


def _block(section_id, title, body):
    return f'::: {{#{section_id} .section intent="bullets"}}\n## {title}\n\n{body}\n:::\n'


@pytest.mark.parametrize("command", ["check", "build"])
@pytest.mark.parametrize("evidence", ["source", "gathered-fact"])
@pytest.mark.parametrize("quotes", [('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’")])
def test_only_verified_quoted_occurrences_escape_the_banned_term_check(tmp_path, capsys, command, evidence, quotes):
    opening, closing = quotes
    quoted = f"{opening}unlock practical progress{closing}"
    unverified = f"{opening}unlock a secret switch{closing}"
    sections = [
        _block(
            "quoted",
            quoted,
            f"The source says {quoted}. [S2]\n\n- **{quoted}** {quoted} [S2]\n  - {quoted}\n\n> spoken: {quoted}",
        ),
        _block("raw", "Ordinary wording", "- unlock practical progress [S2]"),
        _block("unverified", "Unverified wording", f"- {unverified} [S2]"),
        _block("mixed", "Mixed wording", f"The source says {quoted}; we also unlock practical progress. [S2]"),
    ]
    source = "The workshop note says unlock practical progress for everyone."
    sources = [
        "- [S1] A separate note about recording evidence.",
        "- [S2] " + (source if evidence == "source" else "Workshop transcript."),
    ]
    # Exercise both section and evidence orders without changing their associations.
    if command == "build":
        sections.reverse()
        sources.reverse()
    working = tmp_path / "quoted.md"
    working.write_text(
        "---\ndoctype: pitch-deck\nformat: slides\n---\n\n## Sources\n\n"
        + "\n".join(sources)
        + "\n\n"
        + "\n".join(sections),
        encoding="utf-8",
    )
    if evidence == "gathered-fact":
        facts = tmp_path / "gathered.json"
        facts.write_text(
            json.dumps(
                [
                    {"text": "The recording is complete.", "source": "S1"},
                    {"text": source, "source": "S2", "locator": "00:41"},
                ]
            ),
            encoding="utf-8",
        )
        assert main(["facts", "add", str(working), str(facts)]) == 0
        capsys.readouterr()

    code = main([command, str(working)])
    output = capsys.readouterr()
    assert code == (1 if command == "check" else 0), output.out + output.err
    report = (
        tmp_path / "build" / "quoted.findings.json"
        if command == "check"
        else tmp_path / "quoted.versions" / "v1" / "findings.json"
    )
    findings = [f for f in json.loads(report.read_text()) if f["rule_id"] == "source.banned-terms"]
    assert {(f["section_id"], f["measured"]["field"]) for f in findings} == {
        ("raw", "items"),
        ("unverified", "items"),
        ("mixed", "paragraphs"),
    }, "exempt only the verified quotation, including when an unquoted occurrence shares its field"
    assert all(f["measured"]["terms"] == ["unlock"] for f in findings)


def _assert_source_quote_guidance(text):
    # Allow editorial freedom while requiring a usable exception to the voice rule.
    paragraphs = [" ".join(paragraph.lower().split()) for paragraph in re.split(r"\n\s*\n", text)]
    passages = [paragraph for paragraph in paragraphs if "quot" in paragraph and "source" in paragraph]
    assert passages, "state that this exception applies to wording quoted from a source"
    assert any(re.search(r"\b(?:keep\w*|retain\w*|preserv\w*)\b", line) for line in passages), (
        "tell the writer to keep the source's own form"
    )
    assert any("contraction" in line or "don't know" in line or "don’t know" in line for line in passages), (
        "the exception must explicitly cover contractions"
    )


@pytest.mark.parametrize("reverse", [False, True], ids=["target-first", "target-last"])
def test_doc_section_brief_explains_the_source_quote_exception_to_its_voice(tmp_path, capsys, reverse):
    sections = [_block("target", "Findings", "- Record the evidence."), _block("other", "Next steps", "- Review it.")]
    if reverse:
        sections.reverse()
    working = tmp_path / "report.md"
    working.write_text("---\ndoctype: report\nformat: doc\n---\n\n" + "\n".join(sections), encoding="utf-8")
    before = working.read_bytes()

    assert main(["section", "brief", str(working), "target"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "contractions" in captured.out.lower(), "the neutral document voice still avoids contractions"
    _assert_source_quote_guidance(captured.out)
    assert working.read_bytes() == before


def test_write_section_instructions_preserve_source_quotations_including_contractions():
    _assert_source_quote_guidance((ROOT / "agents" / "write-section.md").read_text(encoding="utf-8"))
