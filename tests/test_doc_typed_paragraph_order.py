"""Typed multiline paragraphs retain their position through CLI saves and builds."""

import json
from pathlib import Path

from docx import Document as WordDocument

from ai_docs_kit.cli import main

INTENTS = ("body", "bullets", "callout", "chart", "key-numbers")
DATA = """```data
type: bar
categories: [Upland, Lowland]
series:
  - name: Completed
    values: [17, 29]
```
"""


def working_text():
    sections = []
    for intent in INTENTS:
        content = DATA if intent == "chart" else "- **42%** Survey coverage\n- **120** Completed visits"
        sections.append(
            f'::: {{#{intent} .section intent="{intent}"}}\n## Survey\n\n'
            "Opening prose stays first.\n\n"
            "```paragraph\n|-\n  Multiline opening\n  stays before the figures.\n```\n\n"
            f"{content}\n\n"
            "```paragraph\n|-\n  Multiline closing\n  stays after the figures.\n```\n\n"
            "Closing prose stays last.\n:::\n"
        )
    return "---\ndoctype: report\nformat: doc\n---\n\n" + "\n".join(sections)


def test_typed_and_inline_paragraphs_keep_pdf_word_order_after_repeated_cli_saves(tmp_path, capsys):
    working = tmp_path / "report.md"
    working.write_text(working_text(), encoding="utf-8")
    saved = None
    for _ in range(2):
        for intent in INTENTS:
            assert main(["section", "get", str(working), intent]) == 0
            replacement = tmp_path / "section.md"
            replacement.write_text(capsys.readouterr().out, encoding="utf-8")
            assert main(["section", "put", str(working), intent, "--from", str(replacement)]) == 0
            capsys.readouterr()
        if saved is not None:
            assert working.read_bytes() == saved
        saved = working.read_bytes()
        assert main(["build", str(working)]) == 0
        version = Path(capsys.readouterr().out.strip().splitlines()[-1])
        facts = json.loads((version / "layout.json").read_bytes())
        composition = json.loads((version / "composition.json").read_bytes())
        expected_word = []
        for section in composition["sections"]:
            intent = section["id"]
            middle = ["data"] if intent == "chart" else ["items[0]", "items[1]"]
            assert section["props"]["content_order"] == [
                "paragraphs[0]",
                "paragraphs[1]",
                *middle,
                "paragraphs[2]",
                "paragraphs[3]",
            ]
            words = sorted(
                [word for word in facts["words"] if word["section_id"] == intent],
                key=lambda word: (word["box"]["page"], word["box"]["y0"], word["box"]["x0"]),
            )
            text = " ".join(word["text"] for word in words)
            reading_order = [
                "Opening prose stays first.",
                "Multiline opening stays before the figures.",
                "Upland" if intent == "chart" else "42%",
                "Multiline closing stays after the figures.",
                "Closing prose stays last.",
            ]
            positions = [text.index(part) for part in reading_order]
            assert positions == sorted(positions), text
            for index, paragraph in enumerate(section["props"]["paragraphs"]):
                marks = [
                    mark
                    for mark in facts["marks"]
                    if mark["kind"] == "element"
                    and mark["id"] == intent
                    and mark.get("field") == f"paragraphs[{index}]"
                    and mark["role"] == "paragraph"
                ]
                assert marks
                marked = [
                    word["text"]
                    for word in words
                    if any(
                        word["box"]["page"] == mark["page"]
                        and mark["x"] <= (word["box"]["x0"] + word["box"]["x1"]) / 2 <= mark["x"] + mark["w"]
                        and mark["y"] <= (word["box"]["y0"] + word["box"]["y1"]) / 2 <= mark["y"] + mark["h"]
                        for mark in marks
                    )
                ]
                assert " ".join(paragraph.split()) == " ".join(marked)
            paragraphs = section["props"]["paragraphs"]
            word_middle = (
                ["[Chart 1: Survey]"] if intent == "chart" else ["42%: Survey coverage", "120: Completed visits"]
            )
            expected_word.extend([] if intent == "chart" else ["Survey"])
            expected_word.extend([*paragraphs[:2], *word_middle, *paragraphs[2:]])
        assert [p.text for p in WordDocument(str(version / "report.docx")).paragraphs] == expected_word
