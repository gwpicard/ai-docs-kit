"""Issue 387: judge document page breaks and callout type through the build CLI.

The issue's oracle is the saved version's layout.json, never Typst source text.
No new rule is requested, so each test builds its readable and seeded-defect
cases here. Boundary cases use the neutral A4 frame and its bundled fonts.
"""

import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest
import yaml

from ai_docs_kit.theme import neutral_theme

FRONT = "---\nformat: doc\n---\n\n"
FILLER = "The survey records the route and the access boundary."
HEADING = "Options to consider"
FIRST_TEXT = "The first explanation follows its section heading."
HEAD = (
    "Option A retains the neighbourhood consultation and inspection programme "
    "with a revised route register and a complete record of the survey boundary and access notes"
)
ITEM_BODY = "Publish the complete register after the consultation."
DETAIL = "Further detail explains the survey findings. "
HEADERS = ("Review period", "Visits completed", "Checks recorded")


def _section(ident, intent, heading, blocks):
    return f'::: {{#{ident} .section intent="{intent}"}}\n## {heading}\n\n' + "\n\n".join(blocks) + "\n:::\n\n"


def _build(folder, text, *, theme=None):
    folder.mkdir(parents=True)
    source = folder / "report.md"
    source.write_text(FRONT + text, encoding="utf-8")
    command = [str(Path(sys.executable).with_name("ai-docs-kit")), "build", str(source)]
    if theme is not None:
        command += ["--theme", str(theme)]
    result = subprocess.run(command, cwd=folder, capture_output=True, text=True, check=False, timeout=120)
    assert result.returncode == 0, f"build failed:\n{result.stdout}\n{result.stderr}"
    version = Path(result.stdout.strip().splitlines()[-1])
    assert (version / "report.pdf").is_file()
    facts = json.loads((version / "layout.json").read_text(encoding="utf-8"))
    for page in facts["pages"]:
        image = version / "pages" / f"p{page['page']:02d}.png"
        assert image.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"), "Retain every rendered page for review"
    return facts


def _words(facts, ident, *, role=None, page=None):
    return sorted(
        [
            word
            for word in facts["words"]
            if word["section_id"] == ident
            and (role is None or word["role"] == role)
            and (page is None or word["box"]["page"] == page)
        ],
        key=lambda word: (word["box"]["page"], word["box"]["y0"], word["box"]["x0"]),
    )


def _phrase(words, text):
    expected = text.split()
    matches = [
        words[i : i + len(expected)]
        for i in range(len(words))
        if [word["text"] for word in words[i : i + len(expected)]] == expected
    ]
    assert len(matches) == 1, f"Expected one visible {text!r}, found {len(matches)}"
    return matches[0]


def _mark(facts, ident, field):
    matches = [
        mark
        for mark in facts["marks"]
        if mark["kind"] == "element" and mark["id"] == ident and mark.get("field") == field
    ]
    assert len(matches) == 1, f"Expected one field mark for {ident}/{field}"
    return matches[0]


@pytest.mark.parametrize("intent", ["body", "bullets"])
def test_section_heading_shares_a_page_with_its_first_text(tmp_path, intent):
    for name, count in (("pass", 2), ("fail", 32)):
        background = _section("background", "body", "Background", [FILLER] * count)
        following = FIRST_TEXT + " " + DETAIL * 16
        if intent == "bullets":
            following = "- " + following
        facts = _build(tmp_path / name, background + _section("options", intent, HEADING, [following]))
        heading = _mark(facts, "options", "title")
        field = "paragraphs[0]" if intent == "body" else "items[0]"
        first_text = _mark(facts, "options", field)
        words = _words(facts, "options")
        heading_words = _phrase(words, HEADING)
        text_words = _phrase(words, FIRST_TEXT)
        assert {word["box"]["page"] for word in heading_words} == {heading["page"]}
        assert first_text["page"] == text_words[0]["box"]["page"]
        if name == "pass":
            assert len(facts["pages"]) == 1
        else:
            assert len(facts["pages"]) >= 2, "The seeded document must cross a page boundary"
        assert heading["page"] == first_text["page"], (
            f"{intent} heading stranded on page {heading['page']}; its first text is on page {first_text['page']}"
        )


@pytest.mark.parametrize("intent", ["body", "bullets"])
def test_bold_item_head_shares_a_page_with_the_first_line_of_its_body(tmp_path, intent):
    for name, count in (("pass", 2), ("fail", 32)):
        # The two-line head fills the foot of the page, pushing its body over.
        # A long body may still flow; only its first line belongs with the head.
        item = f"- **{HEAD}** {ITEM_BODY} " + DETAIL * 18
        facts = _build(tmp_path / name, _section("options", intent, "Review options", [*[FILLER] * count, item]))
        words = _words(facts, "options")
        head = _phrase(words, HEAD)
        body = _phrase(words, ITEM_BODY)
        mark = _mark(facts, "options", "items[0]")
        assert mark["page"] == head[0]["box"]["page"]
        if name == "pass":
            assert len(facts["pages"]) == 1
        else:
            assert len(facts["pages"]) >= 2, "The seeded item must reach a page boundary"
        assert {word["box"]["page"] for word in head} == {body[0]["box"]["page"]}, (
            f"{intent} bold item head is stranded before the first body line on page {body[0]['box']['page']}"
        )


def _table(count, reverse):
    rows = [(f"Period {i:02d}", i, i + 100) for i in range(1, count + 1)]
    names = list(HEADERS[1:])
    if reverse:
        rows.reverse()
        names.reverse()
        rows = [(label, previous, current) for label, current, previous in rows]
    data = {
        "type": "bar",
        "category_label": HEADERS[0],
        "categories": [row[0] for row in rows],
        "series": [{"name": name, "values": [row[i] for row in rows]} for i, name in enumerate(names, start=1)],
    }
    chart = _section(
        "monthly", "chart", "Monthly survey register", ["```data\n" + yaml.safe_dump(data, sort_keys=False) + "```"]
    )
    context = _section("context", "body", "Survey context", ["The register records completed visits."])
    return (chart + context if reverse else context + chart), rows


@pytest.mark.parametrize("reverse,count", [(False, 55), (True, 90)], ids=["two-pages", "several-pages-reordered"])
def test_broken_table_repeats_all_headers_above_cells_on_every_continuation(tmp_path, reverse, count):
    for name, row_count in (("pass", 5), ("fail", count)):
        text, rows = _table(row_count, reverse)
        facts = _build(tmp_path / name, text)
        cells = _words(facts, "monthly", role="table-cell")
        expected = Counter(word for row in rows for cell in row for word in str(cell).split())
        assert Counter(word["text"] for word in cells) == expected, "The table must retain every declared cell"
        pages = sorted({word["box"]["page"] for word in cells})
        assert len(pages) == 1 if name == "pass" else len(pages) >= 2
        for page in pages:
            headers = _words(facts, "monthly", role="table-header", page=page)
            assert headers, f"Table continuation page {page} has cells but no repeated header row"
            for label in HEADERS:
                _phrase(headers, label)
            first_cell_top = min(word["box"]["y0"] for word in cells if word["box"]["page"] == page)
            assert max(word["box"]["y1"] for word in headers) <= first_cell_top, (
                f"Page {page} must repeat the headers above its first table row"
            )


@pytest.mark.parametrize("restyled", [False, True], ids=["neutral-body-first", "changed-h1-callout-first"])
def test_callout_label_uses_the_same_theme_h1_size_as_a_body_heading(tmp_path, restyled):
    neutral = neutral_theme()
    expected_size = neutral.tokens.type.scale["doc"].roles["h1"].size
    theme = None
    if restyled:
        theme = tmp_path / "theme"
        shutil.copytree(neutral.root, theme)
        tokens = yaml.safe_load((theme / "tokens.yaml").read_text(encoding="utf-8"))
        expected_size += 7
        tokens["type"]["scale"]["doc"]["h1"]["size"] = expected_size
        (theme / "tokens.yaml").write_text(yaml.safe_dump(tokens, sort_keys=False), encoding="utf-8")

    body = _section("body", "body", "Survey findings", ["The survey records the available options."])
    callout = _section("recommendation", "callout", "Recommendation", ["Keep the register under review."])
    for name in ("pass", "fail"):
        text = body if name == "pass" else (callout + body if restyled else body + callout)
        facts = _build(tmp_path / name, text, theme=theme)
        heading = _phrase(_words(facts, "body", role="heading"), "Survey findings")
        assert all(word["size"] == pytest.approx(expected_size, abs=0.1) for word in heading)
        if name == "fail":
            label = _phrase(_words(facts, "recommendation", role="callout-title"), "Recommendation")
            assert _mark(facts, "recommendation", "title")["role"] == "callout-title"
            assert label[0]["box"]["page"] == heading[0]["box"]["page"], "Compare adjacent headings"
            assert all(word["size"] == pytest.approx(expected_size, abs=0.1) for word in label), (
                f"Callout label must use doc h1 at {expected_size} pt, like its neighbouring body heading; "
                f"got {[word['size'] for word in label]}"
            )
