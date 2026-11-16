import json
import shutil
from pathlib import Path

import pytest
from PIL import Image
from tests.support.fixtures import fixture_path

from ai_docs_kit.cli import main

FIXTURES = {"slides": ("slides", "deck.md"), "doc": ("doc", "report.md")}


def _build(tmp_path: Path, kind: str, capsys) -> tuple[int, str, Path]:
    folder, name = FIXTURES[kind]
    file = tmp_path / name
    shutil.copyfile(fixture_path(folder, name), file)
    code = main(["build", str(file)])
    lines = capsys.readouterr().out.strip().splitlines()
    return code, lines[-1], file


@pytest.fixture(params=sorted(FIXTURES))
def twice(request, tmp_path, capsys):
    kind = request.param
    first = _build(tmp_path, kind, capsys)
    v1_pdf = (Path(first[1]) / f"{first[2].stem}.pdf").read_bytes() if Path(first[1]).is_dir() else b""
    second = _build(tmp_path, kind, capsys)
    return kind, first, second, v1_pdf


def test_every_build_writes_a_version_and_prints_its_path_last(twice):
    kind, (code1, last1, file), (code2, last2, _), _ = twice
    assert code1 == 0 and code2 == 0
    assert Path(last1) == file.parent / f"{file.stem}.versions" / "v1"
    assert Path(last2) == file.parent / f"{file.stem}.versions" / "v2"


def test_version_holds_pdf_manifest_findings_and_one_png_per_page(twice):
    _, (_, last, file), _, _ = twice
    version = Path(last)
    assert (version / f"{file.stem}.pdf").is_file()
    assert (version / "manifest.json").is_file()
    assert isinstance(json.loads((version / "findings.json").read_text()), list)
    index = json.loads((version / "pages" / "pages.json").read_text())
    pngs = sorted(p.name for p in (version / "pages").glob("p*.png"))
    assert len(pngs) == len(index["pages"]) >= 1
    assert pngs == [page["image"] for page in index["pages"]]


def test_pages_json_lists_sections_per_page_and_the_reverse_index(twice):
    _, (_, last, _), _, _ = twice
    index = json.loads((Path(last) / "pages" / "pages.json").read_text())
    by_page = {page["page"]: page["sections"] for page in index["pages"]}
    assert all(by_page.values())
    reverse = index["sections"]
    sections = {s for found in by_page.values() for s in found}
    assert set(reverse) == sections
    for section, pages in reverse.items():
        assert pages == sorted(p for p, found in by_page.items() if section in found)


def test_sheet_matches_the_format(twice):
    kind, (_, last, _), _, _ = twice
    pages = Path(last) / "pages"
    sheet, other = ("contact.png", "spreads.png") if kind == "slides" else ("spreads.png", "contact.png")
    assert (pages / sheet).is_file()
    assert not (pages / other).exists()
    with Image.open(pages / sheet) as image:
        assert image.width > 0 and image.height > 0


def test_second_build_numbers_upwards_and_leaves_the_first_untouched(twice):
    kind, (_, last1, file), (_, last2, _), v1_pdf = twice
    assert last1 != last2
    assert v1_pdf and (Path(last1) / f"{file.stem}.pdf").read_bytes() == v1_pdf
    assert json.loads((Path(last1) / "manifest.json").read_text())["version"] == 1
    assert json.loads((Path(last2) / "manifest.json").read_text())["version"] == 2


def test_findings_do_not_fail_the_build(tmp_path, capsys):
    file = tmp_path / "doc.md"
    shutil.copyfile(fixture_path("seeded-defects", "source.capacity", "fail", "doc.md"), file)
    code = main(["build", str(file)])
    out = capsys.readouterr().out.strip().splitlines()
    assert code == 0
    assert Path(out[-1]).name == "v1"
    assert json.loads((Path(out[-1]) / "findings.json").read_text())


def test_a_failed_build_exits_non_zero_and_writes_no_version(tmp_path, capsys):
    file = tmp_path / "bad.md"
    file.write_bytes(b"\xff\xfe not utf-8")
    assert main(["build", str(file)]) != 0
    assert not (tmp_path / "bad.versions").exists()
