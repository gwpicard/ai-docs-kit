"""An authored font-size check keeps its own minimum when a theme is loaded."""

import json
import shutil

import pdfplumber
import yaml

from ai_docs_kit.cli import main
from ai_docs_kit.theme import NEUTRAL_ROOT


def test_authored_minimum_is_enforced_on_the_rendered_text(tmp_path):
    theme = tmp_path / "theme"
    shutil.copytree(NEUTRAL_ROOT, theme, ignore=shutil.ignore_patterns("exemplars"))
    authored = theme / "rules" / "authored"
    authored.mkdir(parents=True)
    rule = {
        "id": "manual.large-copy",
        "title": "Use larger text",
        "origin": "manual",
        "strength": "hard",
        "status": "active",
        "severity": "error",
        "tier": "geometry",
        "scope": {"format": "doc"},
        "check": {"kind": "font-size", "min_pt": {"doc": 9, "slides": 18}},
        "remedy": {"class": "redraft", "hint": "Use text at least 18 pt."},
        "provenance": {"by": "Dana"},
    }
    path = authored / "large-copy.yaml"
    path.write_text(yaml.safe_dump(rule), encoding="utf-8")
    source = tmp_path / "note.md"
    source.write_text(
        "---\ndoctype: report\nformat: doc\ntitle: Note\n---\n\n"
        '::: {#timing .section intent="body"}\n## Timing\n\nThe plan names a date.\n:::\n',
        encoding="utf-8",
    )
    control = tmp_path / "control"
    assert main(["check", str(source), "--theme", str(theme), "--out", str(control)]) == 0
    assert json.loads((control / "note.findings.json").read_text(encoding="utf-8")) == []
    with pdfplumber.open(control / "note.pdf") as pdf:
        assert any(abs(char["size"] - 11) < 0.01 for page in pdf.pages for char in page.chars)

    rule["check"]["min_pt"]["doc"] = 18
    path.write_text(yaml.safe_dump(rule), encoding="utf-8")
    out = tmp_path / "larger-minimum"
    code = main(["check", str(source), "--theme", str(theme), "--out", str(out)])
    findings = json.loads((out / "note.findings.json").read_text(encoding="utf-8"))

    assert code == 1, f"The 18 pt rule accepted rendered 11 pt text: {findings}"
    hits = [finding for finding in findings if finding["rule_id"] == rule["id"]]
    assert [(hit["section_id"], hit["measured"]["min"]) for hit in hits] == [("timing", 18)]
