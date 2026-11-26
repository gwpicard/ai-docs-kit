"""Front matter stays outside editable sections and their font-size findings."""

import json
import re
import shutil

import yaml

from ai_docs_kit.cli import main
from ai_docs_kit.theme import NEUTRAL_ROOT


def _source(title):
    front = "title: Pilot options review\naudience: Transport committee\n" if title else ""
    return (
        "---\nformat: doc\n" + front + "---\n\n"
        '::: {#front .section intent="body"}\n## Scope\n\nThe review sets out the options.\n:::\n\n'
        '::: {#front_ .section intent="body"}\n## Timing\n\nThe plan names a date.\n:::\n'
    )


def test_page_sections_remain_editable_when_front_matter_has_marks(tmp_path, capsys):
    for titled in (False, True):
        folder = tmp_path / str(titled)
        folder.mkdir()
        source = folder / "report.md"
        source.write_text(_source(titled), encoding="utf-8")
        assert main(["build", str(source)]) == 0
        capsys.readouterr()
        version = folder / "report.versions" / "v1"
        pages = json.loads((version / "pages/pages.json").read_bytes())["pages"]
        assert pages[0]["sections"] == ["front", "front_"]
        first = pages[0]["sections"][0]
        assert main(["section", "get", str(source), first]) == 0
        block = re.search(r"^:::.*?^:::\s*$", capsys.readouterr().out, re.MULTILINE | re.DOTALL)
        assert block is not None
        replacement = folder / "block.md"
        replacement.write_text(block.group(0) + "\n", encoding="utf-8")
        assert main(["section", "put", str(source), first, "--from", str(replacement)]) in (0, 1)
        findings = folder / "findings.json"
        findings.write_text(
            json.dumps(
                [
                    {
                        "severity": "warning",
                        "rule": "look.crowded",
                        "page": 1,
                        "section": first,
                        "message": "The section needs more space.",
                    }
                ]
            ),
            encoding="utf-8",
        )
        assert main(["look", str(version), "--findings", str(findings)]) == 0
        capsys.readouterr()
        assert main(["look", str(version), "--pages"]) == 0
        listing = capsys.readouterr().out
        if titled:
            facts = json.loads((version / "layout.json").read_bytes())
            front_marks = [mark for mark in facts["marks"] if (mark.get("field") or "").startswith("front.")]
            assert {mark["id"] for mark in front_marks} == {"front__"}
            assert {mark["field"] for mark in front_marks} == {"front.title", "front.audience"}
            assert "front.title" in listing and "front.audience" in listing
        else:
            assert "front.title" not in listing and "front.audience" not in listing


def test_authored_font_minimum_reports_sections_without_front_matter(tmp_path, capsys):
    theme = tmp_path / "theme"
    shutil.copytree(NEUTRAL_ROOT, theme, ignore=shutil.ignore_patterns("exemplars"))
    authored = theme / "rules/authored"
    authored.mkdir(parents=True)
    rule = {
        "id": "manual.large-copy",
        "title": "Use larger section text",
        "origin": "manual",
        "strength": "hard",
        "status": "active",
        "severity": "error",
        "tier": "geometry",
        "scope": {"format": "doc"},
        "check": {"kind": "font-size", "min_pt": {"doc": 9, "slides": 18}},
        "remedy": {"class": "redraft", "hint": "Use larger section text."},
        "provenance": {"by": "Dana"},
    }
    rule_path = authored / "large-copy.yaml"
    for titled in (False, True):
        source = tmp_path / f"report-{titled}.md"
        source.write_text(_source(titled), encoding="utf-8")
        for minimum, exit_code in ((9, 0), (18, 1)):
            rule["check"]["min_pt"]["doc"] = minimum
            rule_path.write_text(yaml.safe_dump(rule), encoding="utf-8")
            out = tmp_path / f"check-{titled}-{minimum}"
            assert main(["check", str(source), "--theme", str(theme), "--out", str(out)]) == exit_code
            capsys.readouterr()
            findings = json.loads((out / f"{source.stem}.findings.json").read_bytes())
            hits = [finding for finding in findings if finding["rule_id"] == rule["id"]]
            assert [(hit["section_id"], hit["measured"]["min"]) for hit in hits] == (
                [("front", 18), ("front_", 18)] if minimum == 18 else []
            )
