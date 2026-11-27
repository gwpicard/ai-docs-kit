"""Gathered facts support fresh section drafts through the CLI, without a model call."""

import json
import shutil
from pathlib import Path

import pdfplumber
import pytest

from ai_docs_kit.cli import main
from ai_docs_kit.render.typst import compile_pdf
from ai_docs_kit.theme import neutral_theme

WORKING = """---
doctype: report
format: doc
title: Fleet note
audience: Planning horizon 2031.
---

## Sources

- [S1] fleet-register.pdf, pdf
- [S2] harbour-survey.csv, table
- [S3] operations.vtt, transcript. The baseline count was 73.

::: {#findings .section intent="body"}
## Findings
:::
"""

FACTS = [
    {"text": "Registered vessels totalled 5,232.", "source": "S1", "locator": "p.4"},
    {"text": "Electric propulsion accounted for 42%.", "source": "S2"},
    {"text": "Harbour Trial started on 17 February 2026.", "source": "S3", "locator": "00:41"},
]


def _run(argv, capsys):
    # argparse exits for an absent command; report that as an assertion failure at the caller.
    try:
        code = main(argv)
    except SystemExit as error:
        code = error.code
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _seed(folder: Path, *, sources: bool = True) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "report.md"
    path.write_text(WORKING, encoding="utf-8")
    if sources:
        source = folder / "fleet-register.typ"
        source.write_text("\n#pagebreak()\n".join([FACTS[0]["text"]] * 8), encoding="utf-8")
        compile_pdf(source, folder, folder / "fleet-register.pdf", [neutral_theme().fonts_dir])
        (folder / "harbour-survey.csv").write_text("Vessels,Share\n5232,42%\n", encoding="utf-8")
        (folder / "operations.vtt").write_text(
            "WEBVTT\n\n00:00:41.000 --> 00:00:45.000\n" + FACTS[2]["text"] + "\n", encoding="utf-8"
        )
    return path


def _input(path: Path, facts) -> Path:
    path.write_text(json.dumps(facts), encoding="utf-8")
    return path


def _add(working: Path, incoming: Path, capsys) -> None:
    code, out, err = _run(["facts", "add", str(working), str(incoming)], capsys)
    assert code == 0, f"facts add must accept the gather agent's facts: {out}{err}"
    assert not err


def _list(working: Path, capsys) -> list[str]:
    code, out, err = _run(["facts", "list", str(working)], capsys)
    assert code == 0, f"facts list must read the working file's stored facts: {out}{err}"
    assert not err
    return out.splitlines()


def _assert_listed(lines, facts) -> None:
    assert len(lines) == len(facts), "list must print each stored fact exactly once, without headings"
    for fact in facts:
        matches = [
            line
            for line in lines
            if fact["text"] in line and fact["source"] in line and (not fact.get("locator") or fact["locator"] in line)
        ]
        assert len(matches) == 1, f"list must print text, source key and any locator for {fact!r}: {lines!r}"


def _block(body: str) -> str:
    return f'::: {{#findings .section intent="body"}}\n## Findings\n\n{body}\n:::\n'


def _put(working: Path, replacement: Path, capsys):
    return _run(["section", "put", str(working), "findings", "--from", str(replacement)], capsys)


@pytest.mark.parametrize("reverse", [False, True], ids=["source-order", "reverse-order"])
def test_facts_add_persists_beside_working_file_and_merges_duplicates(tmp_path, capsys, monkeypatch, reverse):
    working = _seed(tmp_path / "project")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    facts = list(reversed(FACTS)) if reverse else FACTS
    first = _input(elsewhere / "first.json", [facts[0], facts[1], facts[0]])
    second = _input(elsewhere / "second.json", [facts[1], facts[2], facts[0]])

    _add(working, first, capsys)
    _add(working, first, capsys)
    _add(working, second, capsys)
    _add(working, second, capsys)
    assert working.read_text(encoding="utf-8") == WORKING
    store = working.parent / ".ai_docs_kit"
    assert store.is_dir(), "facts belong in .ai_docs_kit beside the working file, regardless of cwd"

    # Only the working file and its store travel; neither input JSON file is available here.
    resumed = _seed(tmp_path / "resumed", sources=False)
    shutil.copytree(store, resumed.parent / ".ai_docs_kit")
    first.unlink()
    second.unlink()
    _assert_listed(_list(resumed, capsys), FACTS)


def test_facts_list_keeps_distinct_sources_and_locators_and_accepts_an_omitted_locator(tmp_path, capsys):
    working = _seed(tmp_path)
    facts = [
        FACTS[0],
        {**FACTS[0], "locator": "p.8"},
        {**FACTS[0], "source": "S2", "locator": "harbour-survey!A2"},
        FACTS[1],
        FACTS[2],
    ]
    _add(working, _input(tmp_path / "gathered.json", facts), capsys)
    _assert_listed(_list(working, capsys), facts)


@pytest.mark.parametrize("unknown_first", [True, False], ids=["unknown-first", "unknown-last"])
def test_facts_add_refuses_an_unknown_source_with_one_line_and_exit_two(tmp_path, capsys, unknown_first):
    working = _seed(tmp_path)
    unknown = {"text": "The unlisted source counted 9876 vessels.", "source": "S99", "locator": "p.9"}
    facts = [unknown, FACTS[0]] if unknown_first else [FACTS[0], unknown]
    incoming = _input(tmp_path / "gathered.json", facts)

    code, out, err = _run(["facts", "add", str(working), str(incoming)], capsys)

    assert code == 2
    assert len(err.splitlines()) == 1, f"refuse with one useful line, without usage or a traceback: {err}"
    assert "S99" in err
    assert "Traceback" not in out + err
    assert working.read_text(encoding="utf-8") == WORKING
    assert not any("S99" in line or unknown["text"] in line for line in _list(working, capsys))


@pytest.mark.parametrize("reverse", [False, True], ids=["source-order", "reverse-order"])
def test_section_put_adds_every_stored_fact_and_preserves_the_existing_guard(tmp_path, capsys, reverse):
    working = _seed(tmp_path)
    original = WORKING.replace("## Findings\n", "## Findings\n\nThe earlier count was 61.\n")
    working.write_text(original, encoding="utf-8")
    facts = list(reversed(FACTS)) if reverse else FACTS
    items = [
        f"- {fact['text']} [{fact['source']}" + (f" {fact['locator']}" if fact.get("locator") else "") + "]"
        for fact in facts
    ]
    items.extend(
        ["- The baseline count was 73. [S3]", "- The planning horizon is 2031.", "- The earlier count was 61."]
    )
    supported = _block("\n".join(items))
    replacement = tmp_path / "draft.md"
    replacement.write_text(supported, encoding="utf-8")
    code, _, err = _put(working, replacement, capsys)
    assert code == 1 and "fact-unsupported" in err and "5232" in err.replace(",", "")
    assert working.read_text(encoding="utf-8") == original

    _add(working, _input(tmp_path / "gathered.json", facts), capsys)
    replacement.write_text(supported.replace("5,232", "9,876"), encoding="utf-8")
    code, _, err = _put(working, replacement, capsys)
    assert code == 1
    assert "fact-unsupported" in err and "9876" in err.replace(",", "")
    assert working.read_text(encoding="utf-8") == original

    replacement.write_text(supported, encoding="utf-8")
    code, out, err = _put(working, replacement, capsys)
    assert code == 0, f"stored facts must support figures, dates and names alongside the old evidence: {out}{err}"
    accepted = working.read_text(encoding="utf-8")
    for fact in facts:
        assert fact["text"] in accepted
    for number in ("73", "2031", "61"):
        assert number in accepted

    replacement.write_text(supported.replace("[S1 p.4]", "[S99 p.4]"), encoding="utf-8")
    code, _, err = _put(working, replacement, capsys)
    assert code == 1 and "fact-unsupported" in err and "S99" in err
    assert working.read_text(encoding="utf-8") == accepted


@pytest.mark.parametrize("reverse", [False, True], ids=["count-first", "percentage-first"])
def test_a_fresh_section_drafted_from_stored_facts_builds_a_pdf(tmp_path, capsys, reverse):
    working = _seed(tmp_path)
    facts = list(reversed(FACTS[:2])) if reverse else FACTS[:2]
    paragraphs = [f"{fact['text']} [{fact['source']}]" for fact in facts]
    replacement = tmp_path / "draft.md"
    replacement.write_text(_block("\n\n".join(paragraphs)), encoding="utf-8")
    code, _, err = _put(working, replacement, capsys)
    assert code == 1 and "fact-unsupported" in err
    assert working.read_text(encoding="utf-8") == WORKING

    _add(working, _input(tmp_path / "gathered.json", facts), capsys)
    _assert_listed(_list(working, capsys), facts)
    code, out, err = _put(working, replacement, capsys)
    assert code == 0, f"the first draft must be accepted from stored facts: {out}{err}"
    code, out, err = _run(["build", str(working)], capsys)
    assert code == 0, f"the accepted draft must build through the CLI: {out}{err}"

    pdf = tmp_path / "build" / "report.pdf"
    assert pdf.read_bytes().startswith(b"%PDF-")
    with pdfplumber.open(pdf) as document:
        text = "\n".join(page.extract_text() or "" for page in document.pages)
    for expected in ("5,232", "42%", "Registered vessels", "Electric propulsion"):
        assert expected in text, f"the PDF must contain the gathered fact, not just an empty section: {text}"
    version = tmp_path / "report.versions" / "v1"
    assert (version / "report.pdf").read_bytes() == pdf.read_bytes()
    assert (version / "report.docx").is_file()
