"""Issue 386: build every section's prose and items in working-file order.

The owner's 26 November decision supersedes the paragraphs-first criterion.
Use raw Markdown so a serialiser cannot hide lost input order before build.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

COMPONENTS = {
    "body": "body",
    "bullets": "bullet-list",
    "callout": "callout",
    "chart": "chart-table",
    "figures": "key-figures-strip",
}
FRONT = "---\ndoctype: report\nformat: doc\n---\n\n## Sources\n\n- [S1] Synthetic survey register.\n\n"
DATA = """```data
type: bar
category_label: District
categories: [Upland, Lowland]
series:
  - name: Completed
    values: [17, 29]
```
"""


def _section(ident, intent, blocks):
    return (
        f'::: {{#{ident} .section intent="{intent}"}}\n## {ident.title()} findings\n\n'
        + "\n\n".join(blocks)
        + "\n:::\n"
    )


def _build(folder, source_text):
    source = folder / "report.md"
    source.write_text(source_text, encoding="utf-8")
    result = subprocess.run(
        [str(Path(sys.executable).with_name("ai-docs-kit")), "build", str(source)],
        cwd=folder,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, f"build failed:\n{result.stdout}\n{result.stderr}"
    version = Path(result.stdout.strip().splitlines()[-1])
    assert (version / "report.pdf").is_file()
    assert (version / "report.docx").is_file()
    return version, json.loads((version / "layout.json").read_text(encoding="utf-8"))


def _position(word):
    box = word["box"]
    return box["page"], box["y0"], box["x0"]


def _inside(word, mark):
    box = word["box"]
    return (
        box["page"] == mark["page"]
        and mark["x"] <= (box["x0"] + box["x1"]) / 2 <= mark["x"] + mark["w"]
        and mark["y"] <= (box["y0"] + box["y1"]) / 2 <= mark["y"] + mark["h"]
    )


def _field_words(facts, ident, field, expected, role=None):
    marks = [
        mark
        for mark in facts["marks"]
        if mark["kind"] == "element" and mark["id"] == ident and mark.get("field") == field
    ]
    assert marks, f"{ident} lost the {field} field containing {expected!r}"
    if role:
        assert all(mark["role"] == role for mark in marks), marks
    words = sorted(
        [word for word in facts["words"] if word["section_id"] == ident and any(_inside(word, mark) for mark in marks)],
        key=_position,
    )
    assert expected in " ".join(word["text"] for word in words), f"{ident}/{field} did not draw {expected!r}"
    return words


def _assert_before(earlier, later):
    # Compare page and vertical extent, rather than trusting PDF extraction order.
    end = max((word["box"]["page"], word["box"]["y1"]) for word in earlier)
    start = min((word["box"]["page"], word["box"]["y0"]) for word in later)
    assert end <= start, "Content was drawn in a different order from the working file"


@pytest.fixture(scope="module", params=["prose-first", "interleaved"])
def mixed_build(tmp_path_factory, request):
    folder = tmp_path_factory.mktemp(f"section-content-{request.param}")
    expected = {}
    sections = []
    for ident in COMPONENTS:
        paragraphs = [f"{ident.title()} opening prose survives.", f"{ident.title()} closing prose survives. [S1 p.8]"]
        if ident == "chart":
            blocks = [*paragraphs, DATA]
            fields = ["paragraphs[0]", "paragraphs[1]", "data.categories[0]"]
        elif ident == "figures":
            figures = "- **42%** Survey coverage [S1 p.5]\n- **120** Completed visits [S1 p.6]"
            if request.param == "prose-first":
                blocks = [*paragraphs, figures]
                fields = ["paragraphs[0]", "paragraphs[1]", "items[0].head"]
            else:
                blocks = [figures, *paragraphs]
                fields = ["items[0].head", "paragraphs[0]", "paragraphs[1]"]
        else:
            items = [
                f"- **{ident.title()} lead** Keep the access record. [S1 p.2]",
                "- Confirm the next visit. [S1 p.4]",
            ]
            if ident in {"body", "bullets"}:
                items[0] += "\n  - Retain the route sketch."
            if request.param == "prose-first":
                blocks = [*paragraphs, *items]
                fields = ["paragraphs[0]", "paragraphs[1]", "items[0]", "items[1]"]
            else:
                blocks = [items[0], paragraphs[0], items[1], paragraphs[1]]
                fields = ["items[0]", "paragraphs[0]", "items[1]", "paragraphs[1]"]
            if ident in {"body", "bullets"}:
                fields.insert(fields.index("items[0]") + 1, "items[0].sub[0]")
        intent = "key-numbers" if ident == "figures" else ident
        sections.append(_section(ident, intent, blocks))
        expected[ident] = (paragraphs, fields)
    version, facts = _build(folder, FRONT + "\n".join(sections))
    composition = json.loads((version / "composition.json").read_text(encoding="utf-8"))
    assert {s["id"]: s["component"] for s in composition["sections"]} == COMPONENTS
    return version, facts, expected


@pytest.mark.parametrize("ident", COMPONENTS)
def test_build_draws_all_section_content_with_field_anchors_in_input_order(mixed_build, ident):
    version, facts, expected = mixed_build
    paragraphs, fields = expected[ident]
    visible = {}
    if ident in {"body", "bullets", "callout"}:
        visible["items[0]"] = _field_words(facts, ident, "items[0]", f"{ident.title()} lead Keep the access record.")
        _field_words(facts, ident, "items[0]", "[S1 p.2]")
        if ident in {"body", "bullets"}:
            visible["items[0].sub[0]"] = _field_words(facts, ident, "items[0].sub[0]", "Retain the route sketch.")
        visible["items[1]"] = _field_words(facts, ident, "items[1]", "Confirm the next visit. [S1 p.4]")
    elif ident == "figures":
        visible["items[0].head"] = _field_words(facts, ident, "items[0].head", "42%")
        _field_words(facts, ident, "items[0].body", "Survey coverage")
        second = _field_words(facts, ident, "items[1].head", "120")
        _field_words(facts, ident, "items[1].body", "Completed visits")
        assert {w["box"]["page"] for w in [*visible["items[0].head"], *second]} == {second[0]["box"]["page"]}
        strip = [
            word
            for word in facts["words"]
            if word["section_id"] == ident and (word["role"] or "").startswith("figure-")
        ]
        assert {word["box"]["page"] for word in strip} == {second[0]["box"]["page"]}
        strip_text = " ".join(word["text"] for word in strip)
        assert "[S1 p.5]" in strip_text and "[S1 p.6]" in strip_text
        visible["items[0].head"] = strip
    else:
        visible["data.categories[0]"] = _field_words(facts, ident, "data.categories[0]", "Upland")
        for field, text in {
            "data.category_label": "District",
            "data.categories[1]": "Lowland",
            "data.series[0].name": "Completed",
            "data.series[0].values[0]": "17",
            "data.series[0].values[1]": "29",
        }.items():
            _field_words(facts, ident, field, text)
        visible["data.categories[0]"] = [
            word
            for word in facts["words"]
            if word["section_id"] == ident and word["role"] in {"table-header", "table-cell"}
        ]
    for i, paragraph in enumerate(paragraphs):
        field = f"paragraphs[{i}]"
        visible[field] = _field_words(facts, ident, field, paragraph, role="paragraph")
    for earlier, later in zip(fields, fields[1:], strict=False):
        _assert_before(visible[earlier], visible[later])
    if ident == "callout":
        frame = next(
            m for m in facts["marks"] if m["kind"] == "element" and m["id"] == ident and m["role"] == "callout"
        )
        assert all(_inside(word, frame) for words in visible.values() for word in words), (
            "Prose belongs inside the frame"
        )
    index = json.loads((version / "pages/pages.json").read_text(encoding="utf-8"))
    for page in {word["box"]["page"] for words in visible.values() for word in words}:
        assert page in index["sections"][ident]
        assert (version / "pages" / f"p{page:02d}.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.parametrize("prose_first", [True, False], ids=["prose-before-strip", "prose-after-strip"])
def test_key_number_prose_flows_across_pages_while_the_strip_stays_together(tmp_path, prose_first):
    sentence = "Keep the survey record complete so every route can be checked at the next visit."
    paragraph = "Openingmarker " + " ".join([sentence] * 100) + " Closingmarker."
    strip = "- **42%** Survey coverage\n- **120** Completed visits"
    blocks = [paragraph, strip] if prose_first else [strip, paragraph]
    _, facts = _build(tmp_path, FRONT + _section("figures", "key-numbers", blocks))
    words = [word for word in facts["words"] if word["section_id"] == "figures"]
    # A paragraph's continuation may have no role: its mark starts on an earlier page.
    prose = sorted([word for word in words if word["role"] in {"paragraph", None}], key=_position)
    assert " ".join(word["text"] for word in prose) == paragraph, "Long prose was dropped or clipped"
    assert len({word["box"]["page"] for word in prose}) > 1, "Prose must flow outside the unbreakable strip"
    values = [word for word in words if word["role"] == "figure-value"]
    assert {word["text"] for word in values} == {"42%", "120"}
    assert len({word["box"]["page"] for word in values}) == 1
    _assert_before(prose, values) if prose_first else _assert_before(values, prose)
    pages = {page["page"]: page for page in facts["pages"]}
    for word in words:
        box = word["box"]
        page = pages[box["page"]]
        assert 0 <= box["x0"] < box["x1"] <= page["width"]
        assert 0 <= box["y0"] < box["y1"] <= page["height"]
