"""`review apply` on plans `review read` made from a PowerPoint copy: field text lands in its field."""

import json
import shutil
from pathlib import Path

import pytest
from pptx import Presentation
from tests.support.fixtures import fixture_path

from ai_docs_kit.cli import main
from ai_docs_kit.source.parser import parse


def _run(argv: list[str]) -> int:
    try:
        return main(argv)
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else -1


@pytest.fixture(scope="module")
def sent(tmp_path_factory) -> Path:
    folder = tmp_path_factory.mktemp("applydeck")
    shutil.copyfile(fixture_path("slides", "deck.md"), folder / "deck.md")
    assert main(["build", str(folder / "deck.md")]) == 0
    version = folder / "deck.versions" / "v1"
    empty = folder / "none.json"
    empty.write_text("[]")
    assert main(["look", str(version), "--findings", str(empty)]) == 0
    assert main(["sent", str(version), "--to", "Reviewer"]) == 0
    return folder


@pytest.fixture
def work(sent, tmp_path) -> Path:
    shutil.copytree(sent, tmp_path / "w")
    return tmp_path / "w"


def _set(shape, text: str) -> None:
    runs = [r for p in shape.text_frame.paragraphs for r in p.runs]
    runs[0].text = text
    for run in runs[1:]:
        run.text = ""


def _plan(work: Path, edits: dict[str, str], capsys) -> Path:
    target = work / "deck-reviewed.pptx"
    shutil.copyfile(work / "deck.versions" / "v1" / "deck.pptx", target)
    deck = Presentation(str(target))
    for slide in deck.slides:
        for shape in slide.shapes:
            if shape.name in edits:
                _set(shape, edits[shape.name])
    deck.save(str(target))
    assert main(["review", "read", str(target)]) == 0
    out = capsys.readouterr().out
    return Path([line.split()[-1] for line in out.splitlines() if line.strip().endswith(".json")][-1])


def _sections(work: Path) -> dict:
    doc, _ = parse((work / "deck.md").read_text(encoding="utf-8"))
    return {s.id: s for s in doc.sections}


def test_changed_boxes_land_in_their_fields_and_the_section_is_human_owned(work, capsys):
    plan = _plan(
        work,
        {"cover/paragraphs[0]": "A reworded deck line.", "agenda/items[1].body": "Compare the three options"},
        capsys,
    )
    code = _run(["review", "apply", str(work / "deck.md"), "--plan", str(plan)])
    out = capsys.readouterr()
    assert code == 0, out.err
    touched = json.loads(out.out.rstrip("\n").splitlines()[-1][len("touched ") :])
    assert touched["applied"] == ["cover", "agenda"]
    sections = _sections(work)
    assert sections["cover"].paragraphs == ["A reworded deck line."]
    assert sections["cover"].title == "Readout"
    assert [i.body for i in sections["agenda"].items] == [
        "Explore the findings",
        "Compare the three options",
        "Discuss next steps",
    ]
    assert sections["cover"].owner == sections["agenda"].owner == "human"
    assert sections["statement"].owner is None


def test_a_loose_text_box_edit_lands_in_the_title(work, capsys):
    plan = _plan(work, {"statement/text": "A sharper direction"}, capsys)
    assert _run(["review", "apply", str(work / "deck.md"), "--plan", str(plan)]) == 0
    capsys.readouterr()
    assert _sections(work)["statement"].title == "A sharper direction"


def test_a_field_changed_since_sending_is_refused_naming_the_section(work, capsys):
    plan = _plan(work, {"cover/paragraphs[0]": "A reworded deck line."}, capsys)
    path = work / "deck.md"
    path.write_text(path.read_text().replace("A short deck", "An edited deck"), encoding="utf-8")
    before = path.read_bytes()
    code = _run(["review", "apply", str(path), "--plan", str(plan)])
    err = capsys.readouterr().err
    assert code == 1 and "cover" in err
    assert path.read_bytes() == before
