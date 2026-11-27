"""Keep number words in table evidence through the facts CLI."""

import json

import openpyxl
import pytest

from ai_docs_kit.cli import main


def _add(working, text, locator, capsys):
    fact = {"text": text, "source": "S1"}
    if locator is not None:
        fact["locator"] = locator
    incoming = working.parent / "incoming.json"
    incoming.write_text(json.dumps([fact]), encoding="utf-8")
    code = main(["facts", "add", str(working), str(incoming)])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.mark.parametrize("suffix", ["csv", "xlsx"])
@pytest.mark.parametrize("locator_kind", ["cell", "row", "whole"])
@pytest.mark.parametrize("position", ["header", "body"])
def test_stated_number_words_and_digits_survive_table_selection(tmp_path, capsys, suffix, locator_kind, position):
    for name, value in [("digits", 4), ("words", "four")]:
        folder = tmp_path / name
        folder.mkdir()
        source = folder / f"counts.{suffix}"
        values = [value, "Depots", "seven"] if position == "header" else ["Depots", value, "seven"]
        if suffix == "csv":
            source.write_text("\n".join(str(item) for item in values) + "\n", encoding="utf-8")
        else:
            book = openpyxl.Workbook()
            sheet = book.active
            sheet.title = "counts"
            for item in values:
                sheet.append([item])
            book.save(source)
            book.close()
        working = folder / "report.md"
        working.write_text(
            f"---\ndoctype: report\nformat: doc\n---\n\n## Sources\n\n- [S1] {source.name}, depot counts\n",
            encoding="utf-8",
        )
        row = 1 if position == "header" else 2
        locator = {"cell": f"counts!A{row}", "row": f"counts!{row}", "whole": None}[locator_kind]
        for text in ["There were four depots.", "There were 4 depots."]:
            code, out, err = _add(working, text, locator, capsys)
            assert code == 0 and not err, f"{name} {position} {locator_kind}: {out}{err}"

        store = folder / ".ai_docs_kit" / "facts" / "report.md.json"
        before = store.read_bytes()
        code, out, err = _add(working, "There were eight depots.", locator, capsys)
        assert code == 2 and not out and len(err.splitlines()) == 1
        assert store.read_bytes() == before
        if locator_kind != "whole":
            code, out, err = _add(working, "There were seven depots.", locator, capsys)
            assert code == 2 and not out and len(err.splitlines()) == 1
            assert store.read_bytes() == before
        assert main(["facts", "list", str(working)]) == 0
        listed = capsys.readouterr()
        assert not listed.err and "There were four depots." in listed.out
