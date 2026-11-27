"""Issue 369: writers receive voice rules and the chosen component's limits via the CLI."""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
NEUTRAL = ROOT / "src" / "ai_docs_kit" / "themes" / "neutral"
CUSTOM_VOICE = {
    "summary": {
        "doc": "Use complete sentences and describe evidence before conclusions.",
        "slides": "Use compact phrases and name the practical next step.",
    },
    "banned": ["miracle", "magic shortcut"],
    "terminology": [
        {"preferred": "participant", "avoid": ["user", "consumer"]},
        {"preferred": "check", "avoid": ["audit", "inspection"]},
    ],
}
CAPACITY = {
    "bullet-list": {"title_words": [1, 10], "items": [1, 40], "item_chars": [1, 240]},
    "cards": {"title_words": [1, 8], "items": [2, 4], "item_chars": [10, 100]},
    "bullets": {"title_words": [1, 8], "items": [1, 6], "item_chars": [10, 140]},
}


def _run(folder: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ai_docs_kit.cli", "section", "brief", *args],
        cwd=folder,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _working(folder: Path, fmt: str, reverse: bool, count: int = 3) -> Path:
    intent = "bullets" if fmt == "doc" else "card-set"
    points = [
        "Record the evidence.",
        "Compare the findings.",
        "Agree the next step.",
        "Keep the record.",
        "Check progress.",
    ]
    items = "\n".join(f"- {point}" for point in points[:count])
    blocks = [
        f'::: {{#target .section intent="{intent}"}}\n## Findings\n\n{items}\n:::\n',
        '::: {#other .section intent="bullets"}\n## Other points\n\n- Keep this separate.\n:::\n',
    ]
    if reverse:
        blocks.reverse()
    doctype = "report" if fmt == "doc" else "pitch-deck"
    path = folder / f"working {fmt}.md"
    path.write_text(f"---\ndoctype: {doctype}\nformat: {fmt}\n---\n\n" + "\n".join(blocks), encoding="utf-8")
    return path


def _theme(folder: Path, custom: bool, reverse: bool):
    if not custom:
        voice = yaml.safe_load((NEUTRAL / "voice" / "terminology.yaml").read_text(encoding="utf-8"))
        return [], voice
    theme = folder / "test theme"
    shutil.copytree(NEUTRAL, theme, ignore=shutil.ignore_patterns("exemplars"))
    # Different file and list orders must retain the same associations and complete lists.
    voice = json.loads(json.dumps(CUSTOM_VOICE))
    if reverse:
        voice = dict(reversed(list(voice.items())))
        voice["banned"].reverse()
        voice["terminology"].reverse()
        for term in voice["terminology"]:
            term["avoid"].reverse()
    (theme / "voice" / "terminology.yaml").write_text(yaml.safe_dump(voice, sort_keys=False), encoding="utf-8")
    return ["--theme", str(theme)], voice


def _assert_success(result: subprocess.CompletedProcess[str]) -> str:
    assert result.returncode == 0, f"section brief must succeed: {result.stdout}{result.stderr}"
    assert result.stderr == ""
    assert result.stdout.strip(), "a successful brief must contain the writer's instructions"
    return result.stdout


def _assert_text(text: str, voice, fmt: str, component: str) -> None:
    assert voice["summary"][fmt] in text
    other_format = "slides" if fmt == "doc" else "doc"
    assert voice["summary"][other_format] not in text, "only the working file's format summary belongs in its brief"
    assert re.search(rf"\b{re.escape(component)}\b", text)
    for term in voice["banned"]:
        assert len(re.findall(rf"(?<!\w){re.escape(term)}(?!\w)", text)) == 1, text
    for term in voice["terminology"]:
        for word in [term["preferred"], *term["avoid"]]:
            assert re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text), f"missing terminology {word!r}: {text}"
    for measure, (low, high) in CAPACITY[component].items():
        bounds = rf"{low}\s+to\s+{high}"
        if measure == "item_chars":
            bounds = rf"(?:{bounds}|up\s+to\s+{high})"
        assert re.search(rf"\b{measure}\b[^\n\d]*{bounds}\b", text), f"missing {measure} limits: {text}"
    # A custom theme replaces the neutral voice, rather than appending to it.
    unused = (
        ["leverage", "synergy", "unlock", "journey", "customer", "client"]
        if set(voice["banned"]) == set(CUSTOM_VOICE["banned"])
        else ["miracle", "magic shortcut", "participant", "consumer"]
    )
    for word in unused:
        assert not re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text), f"unexpected voice term {word!r}: {text}"


@pytest.mark.parametrize("fmt", ["doc", "slides"])
@pytest.mark.parametrize("custom", [False, True], ids=["neutral", "custom"])
@pytest.mark.parametrize("reverse", [False, True], ids=["target-first", "target-last"])
@pytest.mark.parametrize("json_mode", [False, True], ids=["text", "json"])
def test_brief_supplies_the_selected_sections_voice_and_capacity(tmp_path, fmt, custom, reverse, json_mode):
    working = _working(tmp_path, fmt, reverse)
    before = working.read_bytes()
    options, voice = _theme(tmp_path, custom, reverse)
    component = "bullet-list" if fmt == "doc" else "cards"

    output = _assert_success(_run(tmp_path, str(working), "target", *options, *(["--json"] if json_mode else [])))
    if json_mode:
        assert output.lstrip().startswith("{"), "--json must print one object without prose or Markdown fences"
        brief = json.loads(output)
        assert brief == {
            "section": "target",
            "intent": "bullets" if fmt == "doc" else "card-set",
            "format": fmt,
            "component": component,
            "voice": voice["summary"][fmt],
            "banned": voice["banned"],
            "terminology": voice["terminology"],
            "capacity": CAPACITY[component],
        }
    else:
        _assert_text(output, voice, fmt, component)
    assert working.read_bytes() == before, "asking for a brief must leave the working file unchanged"


@pytest.mark.parametrize("count", [1, 5])
@pytest.mark.parametrize("reverse", [False, True], ids=["target-first", "target-last"])
def test_brief_uses_content_dependent_chooser_fallback_instead_of_intent_name(tmp_path, count, reverse):
    working = _working(tmp_path, "slides", reverse, count)
    options, voice = _theme(tmp_path, False, reverse)
    text = _assert_success(_run(tmp_path, str(working), "target", *options))
    _assert_text(text, voice, "slides", "bullets")
    brief = json.loads(_assert_success(_run(tmp_path, str(working), "target", "--json")))
    assert brief["intent"] == "card-set"
    assert brief["component"] == "bullets", "cards only fits two to four items; use the chooser's fallback"
    assert brief["capacity"] == CAPACITY["bullets"]


@pytest.mark.parametrize("json_mode", [False, True], ids=["text", "json"])
@pytest.mark.parametrize("missing_file", [False, True], ids=["unknown-id", "missing-file"])
def test_brief_reports_lookup_errors_with_one_stderr_line(tmp_path, json_mode, missing_file):
    working = tmp_path / "missing working.md" if missing_file else _working(tmp_path, "doc", False)
    section_id = "target" if missing_file else "absent-section"
    result = _run(tmp_path, str(working), section_id, *(["--json"] if json_mode else []))
    assert result.returncode == (2 if missing_file else 1), result.stderr
    assert result.stdout == ""
    lines = result.stderr.splitlines()
    assert len(lines) == 1, f"one clear stderr line is required: {result.stderr}"
    assert (working.name if missing_file else section_id) in lines[0]
    assert "Traceback" not in result.stderr


def test_section_brief_help_answers_and_explains_its_options(tmp_path):
    text = _assert_success(_run(tmp_path, "--help"))
    assert "--json" in text
    assert "--theme" in text
    assert "brief" in text


@pytest.mark.parametrize("stage", ["draft", "look"])
def test_create_stages_run_each_sections_brief_and_pass_the_output_to_its_writer(stage):
    text = (ROOT / "skills" / "create" / f"{stage}.md").read_text(encoding="utf-8")
    command = re.search(r"ai-docs-kit\s+section\s+brief\s+<name>\.md\s+<id>", text)
    assert command, f"{stage} must run section brief for the section being written"
    # Inspect the surrounding instructions, allowing numbered steps or paragraphs.
    passage = text[max(0, command.start() - 800) : command.end() + 1000]
    assert re.search(r"(?:each|every|per)\s+(?:\w+\s+){0,3}section\b|section[^.\n]*\b(?:each|every)\b", passage, re.I)
    assert "write-section" in passage
    assert re.search(r"\b(?:give|pass|include|provide|send)\b[^.]*\b(?:output|brief)\b", passage, re.I | re.S), (
        f"{stage} must pass the command's output to write-section, rather than merely naming the command"
    )


def test_write_section_input_names_the_engine_brief():
    text = (ROOT / "agents" / "write-section.md").read_text(encoding="utf-8")
    heading = re.search(r"(?im)^##\s+Input\s*$", text)
    assert heading, "write-section must describe its input"
    inputs = re.split(r"(?m)^##\s+", text[heading.end() :], maxsplit=1)[0]
    assert re.search(r"section\s+brief", inputs, re.I), "the engine's section brief must be part of the agent input"
