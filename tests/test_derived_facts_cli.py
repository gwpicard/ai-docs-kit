"""Issue 370: figures are checked at their source locator before facts are saved."""

import json
import shutil
from pathlib import Path

import pdfplumber
import pytest

from ai_docs_kit.cli import main
from ai_docs_kit.render.typst import compile_pdf
from ai_docs_kit.theme import neutral_theme

FIXTURES = Path(__file__).parent / "fixtures" / "derived-facts"
FIRST = "The service cost 184,000 pounds. The review covered four depots. The share was 42%."
SECOND = "The service ran 61,300 trips. The review covered seven depots. The share was 17%."
WORKING = """---
doctype: report
format: doc
title: Service findings
locale: en-GB
---

## Sources

- [S1] sources/service.pdf, service figures
- [S2] sources/workshop.vtt, discussion transcript
- [S3] sources/routes.csv, route figures
- [S4] sources/notes.md, service notes
- [S5] sources/notes.txt, plain text notes
- [S6] https://example.invalid/service, external service figures
- [S7] sources/missing.md, unavailable notes

::: {#findings .section intent="body"}
## Findings
:::
"""


@pytest.fixture
def project(tmp_path, monkeypatch):
    folder = tmp_path / "project"
    sources = folder / "sources"
    sources.mkdir(parents=True)
    working = folder / "report.md"
    working.write_text(WORKING, encoding="utf-8")
    typst = sources / "service.typ"
    typst.write_text(FIRST + "\n#pagebreak()\n" + SECOND, encoding="utf-8")
    compile_pdf(typst, folder, sources / "service.pdf", [neutral_theme().fonts_dir])
    # Check the generated input independently, so a broken PDF cannot masquerade as a refusal.
    with pdfplumber.open(sources / "service.pdf") as pdf:
        assert len(pdf.pages) == 2
        assert "184,000" in (pdf.pages[0].extract_text() or "")
        assert "61,300" in (pdf.pages[1].extract_text() or "")
    (sources / "workshop.vtt").write_text(
        "WEBVTT\n\nfirst-cue\n00:00:41.000 --> 00:00:45.000\n<v Speaker>"
        + FIRST
        + "\n\nsecond-cue\n00:01:08.000 --> 00:01:12.000\n<v Speaker>"
        + SECOND
        + "\n",
        encoding="utf-8",
    )
    (sources / "routes.csv").write_text(
        'Route,Cost,Trips,Share,Depots\nNorth,"184,000","61,300",42%,four\nSouth,"92,000","31,000",17%,seven\n',
        encoding="utf-8",
    )
    shutil.copyfile(FIXTURES / "source.md", sources / "notes.md")
    (sources / "notes.txt").write_text(FIRST + "\n\n" + SECOND, encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    # Source paths belong to the working file, regardless of the caller's current folder.
    monkeypatch.chdir(elsewhere)
    return working


def _run(*args, capsys):
    try:
        code = main([str(arg) for arg in args])
    except SystemExit as error:
        code = error.code
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _store(working):
    return working.parent / ".ai_docs_kit" / "facts" / f"{working.name}.json"


def _add(working, facts, capsys):
    incoming = working.parent / "incoming.json"
    incoming.write_text(json.dumps(facts), encoding="utf-8")
    return _run("facts", "add", working, incoming, capsys=capsys)


def _accept(working, facts, capsys):
    code, out, err = _add(working, facts, capsys)
    assert code == 0, f"stated figures or supported calculations must be accepted: {out}{err}"
    assert not err, f"readable local evidence needs no warning: {err}"
    _listed(working, facts, capsys)


def _listed(working, facts, capsys):
    code, out, err = _run("facts", "list", working, capsys=capsys)
    assert code == 0, out + err
    assert not err
    for fact in facts:
        assert any(fact["text"] in line and fact["source"] in line for line in out.splitlines()), out
    return out


def _refuse(working, facts, capsys, *, count=1):
    store = _store(working)
    before = store.read_bytes() if store.exists() else None
    original = working.read_bytes()
    code, out, err = _add(working, facts, capsys)
    assert code == 2, f"facts add must refuse unsupported figures before saving the batch: {out}{err}"
    assert not out, f"a refused batch must not report a successful addition: {out}"
    assert len(err.splitlines()) == count, f"report one stderr line per refused fact: {err}"
    assert "Traceback" not in err
    assert (store.read_bytes() if store.exists() else None) == before, "refusal must preserve the store byte for byte"
    assert working.read_bytes() == original
    return err


@pytest.mark.parametrize("reverse", [False, True], ids=["stated-first", "derived-first"])
@pytest.mark.parametrize("existing", [False, True], ids=["new-store", "existing-store"])
def test_seeded_plain_derivation_is_refused_and_calc_twin_is_accepted(project, capsys, reverse, existing):
    passing = json.loads((FIXTURES / "pass.json").read_text(encoding="utf-8"))
    failing = json.loads((FIXTURES / "fail.json").read_text(encoding="utf-8"))
    if existing:
        _accept(project, passing[:1], capsys)
    if reverse:
        failing.reverse()
    err = _refuse(project, failing, capsys)
    assert "S4" in err and "3.00" in err, err

    _accept(project, passing, capsys)
    before = _store(project).read_bytes()
    _accept(project, passing, capsys)
    assert _store(project).read_bytes() == before, "adding the same calc fact twice must not duplicate it"
    listed = _listed(project, passing, capsys)
    assert len(listed.splitlines()) == len(passing)


@pytest.mark.parametrize(
    ("source", "locator", "wrong_locator", "text"),
    [
        ("S1", "p.1", "p.2", "The service cost 184000 pounds."),
        ("S1", "p.2", "p.1", "The service ran 61300 trips."),
        ("S2", "00:41", "01:08", "The share was 42%."),
        ("S2", "01:08", "00:41", "The review covered seven depots."),
        ("S3", "routes!B2", "routes!B3", "North, Cost: 184000"),
        ("S3", "routes!C3", "routes!B3", "South, Trips: 31000"),
    ],
)
def test_stated_figure_must_be_at_the_cited_page_cue_or_cell(project, capsys, source, locator, wrong_locator, text):
    fact = {"text": text, "source": source, "locator": locator}
    _accept(project, [fact], capsys)
    # A figure already stored from elsewhere must not support a false source locator.
    err = _refuse(project, [{**fact, "locator": wrong_locator}], capsys)
    assert source in err, err


@pytest.mark.parametrize("source", ["S1", "S2", "S3", "S4", "S5"])
def test_omitted_locator_checks_the_whole_source(project, capsys, source):
    stated = {"text": "The service cost 184000 and ran 61300 trips.", "source": source}
    _accept(project, [stated], capsys)
    _refuse(project, [{"text": "The service cost 184000 and ran 98765 trips.", "source": source}], capsys)


@pytest.mark.parametrize("source", ["S4", "S5"])
def test_text_and_markdown_use_the_whole_file_even_with_a_locator(project, capsys, source):
    stated = {"text": "The service ran 61300 trips.", "source": source, "locator": "service figures"}
    _accept(project, [stated], capsys)
    _refuse(project, [{**stated, "text": "The service ran 98765 trips."}], capsys)


@pytest.mark.parametrize(
    ("stated", "invented"),
    [
        ("The service cost 184000 pounds.", "The service cost 184001 pounds."),
        ("The share was 42%.", "The share was 42.5%."),
        ("The review covered 4 depots.", "The review covered nine depots."),
        ("The review covered FOUR depots.", "The review covered five depots."),
        ("The share was 42% across four depots.", "The share was 42% across nine depots."),
    ],
)
def test_all_numeric_tokens_use_the_guards_normalisation(project, capsys, stated, invented):
    fact = {"text": stated, "source": "S1", "locator": "p.1"}
    _accept(project, [fact], capsys)
    _refuse(project, [{**fact, "text": invented}], capsys)


@pytest.mark.parametrize("reverse", [False, True])
def test_batch_reports_every_refused_fact_and_saves_none(project, capsys, reverse):
    _accept(project, [{"text": "The service cost £184,000.", "source": "S4"}], capsys)
    facts = [
        {"text": "The service ran 61,300 trips.", "source": "S4"},
        {"text": "The service cost 99999 pounds.", "source": "S1", "locator": "p.1"},
        {"text": "The share was 88% across 99 depots.", "source": "S2", "locator": "00:41"},
    ]
    if reverse:
        facts.reverse()
    err = _refuse(project, facts, capsys, count=2)
    lines = err.splitlines()
    assert any("S1" in line and "99999" in line.replace(",", "") for line in lines), err
    assert any("S2" in line and "88%" in line for line in lines), err
    assert len(_listed(project, [], capsys).splitlines()) == 1


@pytest.mark.parametrize("stored", [False, True], ids=["same-batch-operands", "stored-operands"])
@pytest.mark.parametrize(
    ("expression", "wrong"),
    [
        ("sum(184000, 61300) = 245300", "sum(184000, 61300) = 245301"),
        ("difference(184000, 61300) = 122700", "difference(184000, 61300) = 122701"),
        ("ratio(184000, 61300) = 3.00", "ratio(184000, 61300) = 3.01"),
        ("percentage(184000, 61300) = 300.16%", "percentage(184000, 61300) = 300.17%"),
    ],
)
def test_calc_recomputes_each_operation_from_fact_operands(project, capsys, stored, expression, wrong):
    operands = [
        {"text": "The service cost 184000 pounds.", "source": "S1", "locator": "p.1"},
        {"text": "The service ran 61300 trips.", "source": "S2", "locator": "01:08"},
    ]
    if stored:
        operands.reverse()
        _accept(project, operands, capsys)
        batch = []
    else:
        batch = operands
    calculation = {"text": f"calc: {expression}", "source": "S1"}
    _accept(project, [*batch, calculation], capsys)
    _refuse(project, [{**calculation, "text": f"calc: {wrong}"}], capsys)


@pytest.mark.parametrize("stored_operand", ["cost", "trips", "neither"])
def test_calc_operands_need_facts_not_merely_numbers_in_a_source(project, capsys, stored_operand):
    operands = json.loads((FIXTURES / "pass.json").read_text(encoding="utf-8"))[:2]
    if stored_operand != "neither":
        index = 0 if stored_operand == "cost" else 1
        _accept(project, [operands[index]], capsys)
    # Both numbers are in notes.md, but each must have its own supporting fact.
    _refuse(project, [{"text": "calc: ratio(184000, 61300) = 3.00", "source": "S4"}], capsys)
    _accept(project, [*operands, {"text": "calc: ratio(184000, 61300) = 3.00", "source": "S4"}], capsys)


@pytest.mark.parametrize(
    "wrong",
    ["ratio(184000, 61300) = 184000", "sum(184000, 61300) = 61300", "percentage(184000, 61300) = 42%"],
)
def test_calc_cannot_bypass_arithmetic_when_its_wrong_result_is_stated_in_the_source(project, capsys, wrong):
    operands = json.loads((FIXTURES / "pass.json").read_text(encoding="utf-8"))[:2]
    _accept(project, operands, capsys)
    _refuse(project, [{"text": f"calc: {wrong}", "source": "S1", "locator": "p.1"}], capsys)
    _accept(project, [{"text": "calc: ratio(184000, 61300) = 3.00", "source": "S1"}], capsys)


@pytest.mark.parametrize(
    ("source", "locator", "number"),
    [("S1", "p.2", "2"), ("S2", "00:41", "41"), ("S3", "routes!B2", "2")],
)
def test_locator_metadata_does_not_supply_a_claimed_number(project, capsys, source, locator, number):
    _accept(project, [{"text": "The service cost £184,000.", "source": "S4"}], capsys)
    _refuse(project, [{"text": f"The review covered {number} depots.", "source": source, "locator": locator}], capsys)


@pytest.mark.parametrize("reverse", [False, True])
def test_missing_local_source_is_refused_without_saving_any_of_the_batch(project, capsys, reverse):
    stated = {"text": "The service cost £184,000.", "source": "S4"}
    _accept(project, [stated], capsys)
    batch = [stated, {"text": "The count was 91.", "source": "S7"}]
    if reverse:
        batch.reverse()
    err = _refuse(project, batch, capsys)
    assert "S7" in err and "missing.md" in err, "name the source that cannot be read"


@pytest.mark.parametrize("scheme", ["https", "http"])
def test_url_source_is_accepted_with_a_persistent_unverified_mark_and_warning(project, capsys, scheme):
    url = f"{scheme}://example.invalid/service"
    project.write_text(WORKING.replace("https://example.invalid/service", url), encoding="utf-8")
    fact = {"text": "The external service counted 98765 trips.", "source": "S6", "locator": "p.4"}
    code, out, err = _add(project, [fact], capsys)
    assert code == 0, f"the later owner decision accepts URL evidence: {out}{err}"
    assert "warning" in err.lower() and "unverified" in err.lower(), (
        f"report unverified URL evidence as a warning: {err}"
    )
    assert "S6" in err and url in err, "the warning must identify its unreadable external source"
    listed = _listed(project, [fact], capsys)
    record = next(row for row in json.loads(_store(project).read_bytes()) if row["text"] == fact["text"])
    # The issue leaves the metadata schema open; require a durable mark without fixing a field name.
    assert (
        "unverified" in listed.lower() or "unverified" in json.dumps(record).lower() or record.get("verified") is False
    ), "accepted URL facts must carry a persistent unverified mark"
