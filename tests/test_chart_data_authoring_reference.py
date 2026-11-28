"""Writers can author chart data from the reference without reading engine source."""

import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "skills/create/working-file.md"


def _prose(text):
    lines = []
    fence = None
    for line in text.splitlines():
        match = re.match(r"^\s*(`{3,}|~{3,})(.*)$", line)
        if match and fence is None:
            fence = match[1]
        elif match and match[1][0] == fence[0] and len(match[1]) >= len(fence) and not match[2].strip():
            fence = None
        elif fence is None:
            lines.append(line)
    return "\n".join(lines)


def test_reference_explains_chart_fields_automatic_choice_and_table_fallback():
    text = REFERENCE.read_text(encoding="utf-8")
    prose = " ".join(_prose(text).split())
    for field in ("type", "categories", "series", "name", "values", "unit", "category_label", "time_series", "ordered"):
        assert re.search(rf"\b{field}\b", prose), f"explain the chart data field {field} outside the example"
    assert "ChartData.schema.json" in prose, "point authors at the published chart data schema"
    for kind in ("bar", "column", "line"):
        assert re.search(rf"\b{kind}\b", prose), f"document {kind} as a drawn chart type"
    for topic, pattern in (
        ("numeric values", r"\bnumeric\b|\bnumbers\b"),
        (
            "values corresponding to categories",
            r"categor(?:y|ies)[^.\n]*(?:order|match)|(?:order|match|correspond)[^.\n]*categor",
        ),
        ("omitted type", r"automatic|omit|unspecified|not (?:given|set|supplied)|without[^.\n]*type"),
        ("time-like categories", r"time.like|years?|months?|quarters?"),
        ("negative values", r"negative"),
        ("many categories", r"\b7\b|\bseven\b"),
        ("unsupported type fallback", r"unsupported[^.]*table|cannot[^.]*draw[^.]*table|table[^.]*unsupported"),
    ):
        assert re.search(pattern, prose, re.IGNORECASE), f"explain {topic} in the chart data reference"


def test_reference_has_a_worked_document_chart_and_every_named_command_answers_help():
    text = REFERENCE.read_text(encoding="utf-8")
    # Check the full subcommand path, including facts add/list and section get/put.
    commands = set(re.findall(r"ai-docs-kit\s+([a-z][a-z0-9-]*(?:\s+[a-z][a-z0-9-]*)*)", text))
    assert commands, "the reference must keep its authoring commands"
    for command in sorted(commands):
        done = subprocess.run(
            [sys.executable, "-m", "ai_docs_kit.cli", *command.split(), "--help"],
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=30,
        )
        assert done.returncode == 0, f"{command} --help: {done.stdout}\n{done.stderr}"
        assert "usage:" in done.stdout.lower(), command

    sections = re.findall(
        r"^::: \{[^\n]*\bintent=(?:\"chart\"|chart)[^\n]*\}\s*\n.*?^:::\s*$", text, re.MULTILINE | re.DOTALL
    )
    assert sections, "add a worked chart section for a doc working file, with a heading and fenced data"
    assert re.search(r"(?m)^format:\s*doc\s*$", text), "the worked section belongs in a doc working file"
    worked = []
    for section in sections:
        assert re.search(r"(?m)^##\s+\S", section), "give the worked chart a title"
        blocks = re.findall(r"^```data\s*\n(.*?)^```\s*$", section, re.MULTILINE | re.DOTALL)
        assert blocks, "the worked chart needs a usable YAML data block"
        worked.extend(yaml.safe_load(block) for block in blocks)
    assert any(data.get("categories") and data.get("series") for data in worked)
