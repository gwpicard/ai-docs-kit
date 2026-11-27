"""Issue 367: document title blocks through the build and look commands.

The clock seam is render.compose.build_date() -> datetime.date. Tests supply
calendar dates, leaving British date formatting to the real build path.
"""

import json
import shutil
from datetime import date
from pathlib import Path

import pytest
import yaml

from ai_docs_kit.cli import main
from ai_docs_kit.model import Document, Section
from ai_docs_kit.render import compose as composition
from ai_docs_kit.render.swatch import swatch
from ai_docs_kit.testing.golden import compare_facts
from ai_docs_kit.theme import neutral_theme

FIXTURES = Path(__file__).parent / "fixtures" / "components"
TITLE = "Pilot options review"
AUDIENCE = "Transport committee"
LONG_TITLE = (
    "Review of the transport pilot and the options for extending the service, "
    "changing its scope or ending the trial after the current review period"
)


def _source(title=TITLE, audience=AUDIENCE, *, reverse=False, fmt="doc"):
    front = {"format": fmt}
    if title is not None:
        front["title"] = title
    if audience is not None:
        front["audience"] = audience
    if reverse:
        front = dict(reversed(front.items()))
    sections = [("scope", "Scope of the review"), ("options", "Options to consider")]
    if reverse:
        sections.reverse()
    intent = "body" if fmt == "doc" else "statement"
    body = "\n\nThe review sets out the available options." if fmt == "doc" else ""
    return (
        "---\n"
        + yaml.safe_dump(front, sort_keys=False)
        + "---\n\n"
        + "\n\n".join(
            f'::: {{#{ident} .section intent="{intent}"}}\n## {heading}{body}\n:::' for ident, heading in sections
        )
        + "\n"
    )


def _build(folder, text, capsys, *, theme=None):
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / "report.md"
    source.write_text(text, encoding="utf-8")
    args = ["build", str(source)]
    if theme is not None:
        args += ["--theme", str(theme)]
    code = main(args)
    captured = capsys.readouterr()
    assert code == 0, (captured.out, captured.err)
    version = Path(captured.out.strip().splitlines()[-1])
    assert (version / "report.pdf").is_file()
    assert (version / "pages" / "p01.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    return version, json.loads((version / "layout.json").read_text(encoding="utf-8"))


def _phrase(facts, text):
    words = facts["words"]
    expected = text.split()
    matches = [
        words[i : i + len(expected)]
        for i in range(len(words))
        if [word["text"] for word in words[i : i + len(expected)]] == expected
    ]
    assert len(matches) == 1, f"Expected one visible {text!r}; found {len(matches)} in the PDF"
    return matches[0]


def _heading(facts, reverse=False):
    ident = "options" if reverse else "scope"
    marks = [
        mark
        for mark in facts["marks"]
        if mark["kind"] == "element" and mark["id"] == ident and mark.get("field") == "title"
    ]
    assert len(marks) == 1, "The first section must still have its heading mark"
    assert marks[0]["page"] == 1, "The title block must share page 1 with the first section"
    return marks[0]


def _above(upper, lower):
    assert {word["box"]["page"] for word in upper + lower} == {1}
    assert max(word["box"]["y1"] for word in upper) <= min(word["box"]["y0"] for word in lower)


def _no_front_block(facts, *, audience=AUDIENCE):
    assert not [mark for mark in facts["marks"] if (mark.get("field") or "").startswith("front.")]
    text = " ".join(word["text"] for word in facts["words"])
    assert audience not in text
    assert "26 November 2026" not in text


@pytest.fixture
def fixed_date(monkeypatch):
    # Raising=False lets the unbuilt feature fail on rendered behaviour, not an absent import.
    monkeypatch.setattr(composition, "build_date", lambda: date(2026, 11, 26), raising=False)


@pytest.mark.parametrize("reverse", [False, True], ids=["short-title", "long-title-reordered"])
def test_build_draws_title_audience_and_british_date_above_the_first_section(tmp_path, capsys, fixed_date, reverse):
    _, control = _build(tmp_path / "untitled", _source(title=None, reverse=reverse), capsys)
    _no_front_block(control)
    _heading(control, reverse)

    title = LONG_TITLE if reverse else TITLE
    _, facts = _build(tmp_path / "titled", _source(title=title, reverse=reverse), capsys)
    heading = _heading(facts, reverse)
    title_words = _phrase(facts, title)
    audience_words = _phrase(facts, AUDIENCE)
    date_words = _phrase(facts, "26 November 2026")
    _above(title_words, audience_words)
    _above(audience_words, date_words)
    assert max(word["box"]["y1"] for word in date_words) <= heading["y"]
    assert len(facts["pages"]) == 1, "A short report must not gain a separate cover page"


@pytest.mark.parametrize("audience", [None, ""], ids=["missing-audience", "empty-audience"])
def test_optional_front_fields_and_slides_keep_their_existing_behaviour(tmp_path, capsys, fixed_date, audience):
    for index, title in enumerate((None, "")):
        _, untitled = _build(tmp_path / f"untitled-{index}", _source(title=title), capsys)
        _no_front_block(untitled)
        _heading(untitled)
        assert len(untitled["pages"]) == 1

    _, slides = _build(tmp_path / "slides", _source(fmt="slides"), capsys)
    _, plain_slides = _build(tmp_path / "plain-slides", _source(title=None, audience=None, fmt="slides"), capsys)
    _no_front_block(slides)
    assert TITLE not in " ".join(word["text"] for word in slides["words"])
    assert slides["marks"] == plain_slides["marks"]
    assert slides["words"] == plain_slides["words"]
    assert len(slides["pages"]) == len(plain_slides["pages"]) == 2

    _, facts = _build(tmp_path / "title-only", _source(audience=audience), capsys)
    assert len(facts["pages"]) == 1
    assert not [mark for mark in facts["marks"] if mark.get("field") == "front.audience"]
    title_words = _phrase(facts, TITLE)
    date_words = _phrase(facts, "26 November 2026")
    _above(title_words, date_words)
    assert max(word["box"]["y1"] for word in date_words) <= _heading(facts)["y"]
    expected = TITLE.split() + "26 November 2026".split()
    before_section = [word["text"] for word in facts["words"] if word["box"]["y1"] <= _heading(facts)["y"]]
    assert before_section == expected, "Without audience, only the title and date belong above the first section"


def test_each_build_reads_the_clock_and_keeps_the_previous_versions_date(tmp_path, capsys, monkeypatch):
    _, control = _build(tmp_path / "untitled", _source(title=None), capsys)
    _no_front_block(control)
    previous_version = None
    previous_layout = None
    for day, expected in ((date(2026, 11, 26), "26 November 2026"), (date(2027, 2, 3), "3 February 2027")):
        monkeypatch.setattr(composition, "build_date", lambda day=day: day, raising=False)
        version, facts = _build(tmp_path / "dated", _source(), capsys)
        assert {word["box"]["page"] for word in _phrase(facts, expected)} == {1}
        if previous_version is not None:
            assert (previous_version / "layout.json").read_bytes() == previous_layout
            assert "26 November 2026" not in " ".join(word["text"] for word in facts["words"])
        previous_version = version
        previous_layout = (version / "layout.json").read_bytes()


def test_title_block_sizes_and_colours_follow_changed_document_tokens(tmp_path, capsys, fixed_date):
    neutral = neutral_theme()
    theme = tmp_path / "theme"
    shutil.copytree(neutral.root, theme)
    data = yaml.safe_load((theme / "tokens.yaml").read_text(encoding="utf-8"))
    roles = neutral.tokens.type.scale["doc"].roles
    for name, role in roles.items():
        data["type"]["scale"]["doc"][name]["size"] = role.size + 3
    replacements = {}
    for index, (name, old) in enumerate(neutral.tokens.colour.roles.items(), start=1):
        # Keep roles with the same original colour equivalent in the test theme.
        replacements.setdefault(old, f"#{index * 17:02X}2543")
        data["colour"]["roles"][name] = replacements[old]
    (theme / "tokens.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    _, control = _build(tmp_path / "untitled", _source(title=None), capsys, theme=theme)
    _no_front_block(control)
    for word in _phrase(control, "Scope of the review"):
        assert word["size"] == pytest.approx(roles["h1"].size + 3, abs=0.1)
        assert word["colour"] == replacements[neutral.tokens.colour.roles["ink"]]
    _, original = _build(tmp_path / "neutral", _source(), capsys)
    _, restyled = _build(tmp_path / "restyled", _source(), capsys, theme=theme)
    for text in (TITLE, AUDIENCE, "26 November 2026"):
        before, after = _phrase(original, text), _phrase(restyled, text)
        for old, new in zip(before, after, strict=True):
            assert any(abs(old["size"] - role.size) < 0.1 for role in roles.values()), old
            assert new["size"] == pytest.approx(old["size"] + 3, abs=0.1), "Use the document type scale"
            assert old["colour"] in replacements, "The title block must use a theme colour role"
            assert new["colour"] == replacements[old["colour"]], "Use the changed colour token"


def test_front_marks_enclose_their_text_and_are_named_by_the_look_listing(tmp_path, capsys, fixed_date):
    control, facts = _build(tmp_path / "untitled", _source(title=None), capsys)
    _no_front_block(facts)
    stored = json.loads((control / "composition.json").read_text(encoding="utf-8"))
    legacy = composition.Composition.model_validate({key: stored[key] for key in ("format", "sections")})
    assert len(legacy.sections) == 2, "Older compositions must remain readable without front matter or a date"
    assert main(["look", str(control), "--pages"]) == 0
    assert "front." not in capsys.readouterr().out

    version, facts = _build(tmp_path / "titled", _source(), capsys)
    for field, text in (("front.title", TITLE), ("front.audience", AUDIENCE)):
        marks = [mark for mark in facts["marks"] if mark["kind"] == "element" and mark.get("field") == field]
        assert len(marks) == 1, f"The title block needs an element mark for {field}"
        mark = marks[0]
        assert mark["id"] not in {"scope", "options"}, "Front matter is outside the document's sections"
        assert mark["page"] == 1 and mark["w"] > 0 and mark["h"] > 0
        for word in _phrase(facts, text):
            box = word["box"]
            assert box["page"] == mark["page"]
            assert mark["x"] - 1 <= box["x0"] <= box["x1"] <= mark["x"] + mark["w"] + 1
            assert mark["y"] - 1 <= box["y0"] <= box["y1"] <= mark["y"] + mark["h"] + 1
            assert word["section_id"] == mark["id"] and word["role"] == mark["role"]
        assert mark["y"] + mark["h"] <= _heading(facts)["y"]
    assert main(["look", str(version), "--pages"]) == 0
    listing = capsys.readouterr().out
    assert "front.title" in listing and "front.audience" in listing, listing


@pytest.mark.parametrize("name", ["body", "callout"])
def test_swatches_keep_their_golden_layout_while_the_full_document_gains_a_title(tmp_path, capsys, fixed_date, name):
    before = {path.name: path.read_bytes() for path in FIXTURES.iterdir() if path.is_file()}
    section = Section.model_validate(yaml.safe_load((FIXTURES / f"{name}.yaml").read_text(encoding="utf-8")))
    doc = Document(front={"title": TITLE, "audience": AUDIENCE}, format="doc", sections=[section])
    rendered = swatch(doc, section.id, tmp_path, theme=neutral_theme())
    facts = rendered.facts.model_dump(mode="json")
    _no_front_block(facts)
    assert TITLE not in " ".join(word["text"] for word in facts["words"])
    actual = {}
    for mark in facts["marks"]:
        if mark["kind"] == "element":
            actual.setdefault(mark["role"], {"marks": [], "words": []})["marks"].append(
                {
                    "page": mark["page"],
                    "x0": mark["x"],
                    "y0": mark["y"],
                    "x1": mark["x"] + mark["w"],
                    "y1": mark["y"] + mark["h"],
                }
            )
    for word in facts["words"]:
        if word["role"] is not None:
            actual.setdefault(word["role"], {"marks": [], "words": []})["words"].append(
                {**word["box"], "text": word["text"]}
            )
    golden = json.loads((FIXTURES / f"{name}.facts.json").read_text(encoding="utf-8"))
    assert compare_facts(actual, golden) == []
    assert {path.name: path.read_bytes() for path in FIXTURES.iterdir() if path.is_file()} == before

    _, full = _build(tmp_path / "full", _source(), capsys)
    _phrase(full, TITLE)
