"""Keep headings across document components and let long headed items flow."""

import pytest

from test_doc_page_breaks import (
    DETAIL,
    FILLER,
    FIRST_TEXT,
    HEAD,
    HEADING,
    ITEM_BODY,
    _build,
    _mark,
    _phrase,
    _section,
    _words,
)


@pytest.mark.parametrize("intent", ["chart", "key-numbers"])
def test_figure_section_heading_stays_with_opening_prose(tmp_path, intent):
    data = (
        "```data\ntype: bar\ncategories: [North, South]\nseries:\n  - name: Visits\n    values: [12, 18]\n```"
        if intent == "chart"
        else "- **12** Northern visits\n- **18** Southern visits"
    )
    for name, count in (("pass", 2), ("fail", 32)):
        background = _section("background", "body", "Background", [FILLER] * count)
        following = FIRST_TEXT + " " + DETAIL * 16
        facts = _build(tmp_path / name, background + _section("options", intent, HEADING, [following, data]))
        heading = _mark(facts, "options", "title")
        prose = _mark(facts, "options", "paragraphs[0]")
        assert heading["page"] == prose["page"]
        assert {word["box"]["page"] for word in _phrase(_words(facts, "options"), HEADING)} == {prose["page"]}
        assert len(facts["pages"]) == 1 if name == "pass" else len(facts["pages"]) >= 2


@pytest.mark.parametrize("intent", ["body", "bullets"])
def test_head_keeps_first_body_line_but_allows_later_lines_to_flow(tmp_path, intent):
    for name, repeats in (("pass", 2), ("fail", 150)):
        label = "Option A" if name == "pass" else HEAD
        item = f"- **{label}** {ITEM_BODY} " + DETAIL * repeats
        background = [] if name == "pass" else [FILLER] * 32
        facts = _build(tmp_path / name, _section("options", intent, "Review options", [*background, item]))
        words = _words(facts, "options")
        head = _phrase(words, label)
        body = _phrase(words, ITEM_BODY)
        assert {word["box"]["page"] for word in head} == {body[0]["box"]["page"]}
        # The short item remains inline; keeping the head must not add a line break.
        if name == "pass":
            assert head[-1]["box"]["y0"] == pytest.approx(body[0]["box"]["y0"], abs=0.5)
        else:
            assert max(word["box"]["page"] for word in words) > body[0]["box"]["page"], (
                "The final item must continue beyond its opening page"
            )
        assert len(facts["pages"]) == 1 if name == "pass" else len(facts["pages"]) >= 2
        assert {word["box"]["page"] for word in words} == set(range(1, len(facts["pages"]) + 1))
