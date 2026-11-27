"""Exercise ordering and source failures through the facts CLI."""

import json

import openpyxl
import pytest

from ai_docs_kit.cli import main


def _project(tmp_path, source):
    working = tmp_path / "report.md"
    working.write_text(
        f"---\ndoctype: report\nformat: doc\n---\n\n## Sources\n\n- [S1] {source}, service figures\n",
        encoding="utf-8",
    )
    return working


def _add(working, facts, capsys):
    incoming = working.parent / "incoming.json"
    incoming.write_text(json.dumps(facts), encoding="utf-8")
    code = main(["facts", "add", str(working), str(incoming)])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _store(working):
    return working.parent / ".ai_docs_kit" / "facts" / f"{working.name}.json"


def test_calculations_need_earlier_facts_and_can_use_an_earlier_result(tmp_path, capsys):
    (tmp_path / "notes.md").write_text("The cost was 184000. There were 61300 trips.", encoding="utf-8")
    working = _project(tmp_path, "notes.md")
    cost = {"text": "The cost was 184000.", "source": "S1"}
    trips = {"text": "There were 61300 trips.", "source": "S1"}
    ratio = {"text": "calc: ratio(184000, 61300) = 3.00", "source": "S1"}
    code, out, err = _add(working, [ratio, cost, trips], capsys)
    assert code == 2 and not out and len(err.splitlines()) == 1
    assert "earlier fact" in err
    assert not _store(working).exists()

    chained = {"text": "calc: sum(3.00, 3.00) = 6.00", "source": "S1"}
    code, out, err = _add(working, [cost, trips, ratio, chained], capsys)
    assert code == 0 and "added 4" in out and not err
    before = _store(working).read_bytes()
    code, out, err = _add(working, [{**ratio, "text": "calc: ratio(184000, 61300) = 3.00 trailing"}], capsys)
    assert code == 2 and not out and len(err.splitlines()) == 1
    assert _store(working).read_bytes() == before


@pytest.mark.parametrize("suffix", ["csv", "xlsx"])
def test_table_rows_keep_figures_on_the_cited_row(tmp_path, capsys, suffix):
    source = tmp_path / f"route figures.{suffix}"
    sheet = "'route figures'"
    if suffix == "csv":
        source.write_text("Route,Cost,Trips\nNorth,184000,61300\nSouth,92000,31000\n", encoding="utf-8")
    else:
        book = openpyxl.Workbook()
        table = book.active
        table.title = "route figures"
        for row in [("Route", "Cost", "Trips"), ("North", 184000, 61300), ("South", 92000, 31000)]:
            table.append(row)
        book.save(source)
        book.close()
    working = _project(tmp_path, source.name)
    fact = {"text": "The cost was 184000 for 61300 trips.", "source": "S1", "locator": f"{sheet}!2"}
    code, out, err = _add(working, [fact], capsys)
    assert code == 0 and not err
    before = _store(working).read_bytes()
    code, out, err = _add(working, [{**fact, "locator": f"{sheet}!3"}], capsys)
    assert code == 2 and not out and len(err.splitlines()) == 1
    assert _store(working).read_bytes() == before
    code, out, err = _add(working, [{**fact, "locator": f"{sheet}!2:2"}], capsys)
    assert code == 0 and not err


@pytest.mark.parametrize("name", ["broken.pdf", "broken.xlsx", "broken.md"])
def test_unreadable_source_refuses_even_a_fact_without_figures(tmp_path, capsys, name):
    source = tmp_path / name
    source.write_bytes(b"\xff")
    working = _project(tmp_path, name)
    fact = {"text": "The service is under review.", "source": "S1"}
    code, out, err = _add(working, [fact], capsys)
    assert code == 2 and not out and len(err.splitlines()) == 1
    assert name in err and "Traceback" not in err
    assert not _store(working).exists()

    source = tmp_path / "readable.md"
    source.write_text("The service is under review.", encoding="utf-8")
    working = _project(tmp_path, source.name)
    code, out, err = _add(working, [fact], capsys)
    assert code == 0 and not err


def test_url_verification_is_set_by_the_engine_and_survives_repeated_additions(tmp_path, capsys):
    working = _project(tmp_path, "https://example.invalid/figures")
    fact = {"text": "There were 98765 trips.", "source": "S1", "verification": "verified"}
    for count in [1, 0]:
        code, out, err = _add(working, [fact], capsys)
        assert code == 0 and f"added {count}" in out
        assert "warning" in err and "unverified" in err and "https://example.invalid/figures" in err
        records = json.loads(_store(working).read_bytes())
        assert len(records) == 1 and records[0]["verification"] == "unverified"
        # An older store can lack the optional mark; adding again must restore it.
        records[0].pop("verification")
        _store(working).write_text(json.dumps(records), encoding="utf-8")

    code, out, err = _add(working, [fact], capsys)
    assert code == 0 and "added 0" in out and "unverified" in err
    assert json.loads(_store(working).read_bytes())[0]["verification"] == "unverified"

    before = _store(working).read_bytes()
    code, out, err = _add(working, [{"text": "calc: sum(98765, 98765) = 1", "source": "S1"}], capsys)
    assert code == 2 and not out and len(err.splitlines()) == 1
    assert _store(working).read_bytes() == before
