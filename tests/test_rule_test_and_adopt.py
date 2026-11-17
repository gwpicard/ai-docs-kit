"""`rule test` and `rule adopt`: a rule proposed from a comment is tested, then adopted on probation.

Shapes these tests pin (recorded under Deviations in PLAN.md): `--example` is the version folder, a
slash and a section id; the example's text is read from the version's `composition.json`. The
theme's approved exemplars are the working files under `<theme>/exemplars/gold`. `rule test` prints
one line per hit holding the file or version and the section id. `rule adopt` writes the rule to
`<theme>/rules/learned/`, where the theme loader reads feedback rules.
"""

import json
import shutil
from pathlib import Path

import pytest
import yaml

from ai_docs_kit.cli import main
from ai_docs_kit.theme import NEUTRAL_ROOT

REVIEW_COPY = "note.review.docx"
AUTHOR = "Dana Reviewer"
COMMENT_DATE = "2026-11-10"

NOTE = """---
doctype: report
format: doc
title: Note
---

::: {{#bad01 .section intent="body"}}
## Timing

{bad}
:::

::: {{#fine01 .section intent="body"}}
## Scope

The plan covers the pipeline readings.
:::
"""

EXEMPLAR = """---
doctype: report
format: doc
title: Exemplar
---

::: {#gold01 .section intent="body"}
## Approved

The plan covers the approved readings and names a date.
:::
"""


def _rule(regex: str, severity: str = "error") -> dict:
    return {
        "id": "feedback.no-asap",
        "title": "Do not write ASAP",
        "origin": "feedback",
        "strength": "soft",
        "status": "proposed",
        "severity": severity,
        "tier": "source",
        "check": {"kind": "text-pattern", "field": "paragraphs", "regex": regex},
        "remedy": {"class": "redraft", "hint": "Give a date instead."},
        "provenance": {
            "label": "answered",
            "source": {"review_copy": REVIEW_COPY, "comment": "Never write ASAP."},
            "created": COMMENT_DATE,
            "by": AUTHOR,
        },
    }


def _write_rule(folder: Path, regex: str, name: str = "rule.yaml", severity: str = "error") -> Path:
    path = folder / name
    path.write_text(yaml.safe_dump(_rule(regex, severity)), encoding="utf-8")
    return path


@pytest.fixture
def theme(tmp_path) -> Path:
    root = tmp_path / "theme"
    shutil.copytree(NEUTRAL_ROOT, root, ignore=shutil.ignore_patterns("exemplars"))
    gold = root / "exemplars" / "gold"
    gold.mkdir(parents=True)
    (gold / "approved.md").write_text(EXEMPLAR, encoding="utf-8")
    return root


def _build(tmp_path: Path, theme: Path, bad: str = "Please reply ASAP about the plan.") -> Path:
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    (work / "note.md").write_text(NOTE.format(bad=bad), encoding="utf-8")
    assert main(["build", str(work / "note.md"), "--theme", str(theme)]) == 0
    return work / "note.versions" / "v1"


@pytest.fixture
def version(tmp_path, theme) -> Path:
    return _build(tmp_path, theme)


def _run(argv: list[str]) -> int:
    try:
        return main(argv)
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else 2


def _test(rule: Path, version: Path, theme: Path, section: str = "bad01") -> int:
    return _run(["rule", "test", str(rule), "--example", f"{version}/{section}", "--theme", str(theme)])


def _adopt(rule: Path, theme: Path) -> int:
    return _run(["rule", "adopt", str(rule), "--theme", str(theme)])


def _learned(theme: Path) -> list[Path]:
    return sorted((theme / "rules" / "learned").glob("*.yaml"))


def test_a_rule_that_fires_on_the_example_only_passes(tmp_path, theme, version, capsys):
    rule = _write_rule(tmp_path, r"\bASAP\b")
    assert _test(rule, version, theme) == 0


def test_a_rule_that_misses_the_example_fails(tmp_path, theme, version, capsys):
    rule = _write_rule(tmp_path, r"\bNEVERWRITTEN\b")
    assert _test(rule, version, theme) == 1


def test_the_same_rule_misses_a_section_it_does_not_fire_on(tmp_path, theme, version, capsys):
    rule = _write_rule(tmp_path, r"\bASAP\b")
    assert _test(rule, version, theme, section="fine01") == 1


def test_a_rule_that_also_fires_on_an_exemplar_fails_and_lists_the_hit(tmp_path, theme, version, capsys):
    rule = _write_rule(tmp_path, r"\bplan\b")
    assert _test(rule, version, theme) == 1
    out = capsys.readouterr().out
    assert "approved.md" in out
    assert "gold01" in out


def test_every_hit_is_listed(tmp_path, theme, capsys):
    gold = theme / "exemplars" / "gold"
    (gold / "second.md").write_text(EXEMPLAR.replace("gold01", "gold02"), encoding="utf-8")
    version = _build(tmp_path, theme)
    rule = _write_rule(tmp_path, r"\bplan\b")
    assert _test(rule, version, theme) == 1
    out = capsys.readouterr().out
    assert "gold01" in out
    assert "gold02" in out


def test_a_rule_that_fires_on_the_example_and_an_exemplar_is_not_adopted(tmp_path, theme, version):
    rule = _write_rule(tmp_path, r"\bplan\b")
    assert _test(rule, version, theme) == 1
    assert _adopt(rule, theme) == 1
    assert _learned(theme) == []


def test_a_missing_rule_file_exits_2(tmp_path, theme, version, capsys):
    assert _test(tmp_path / "none.yaml", version, theme) == 2
    assert "none.yaml" in capsys.readouterr().err


def test_a_missing_section_exits_2(tmp_path, theme, version, capsys):
    rule = _write_rule(tmp_path, r"\bASAP\b")
    assert _test(rule, version, theme, section="nosuch1") == 2
    assert "nosuch1" in capsys.readouterr().err


def test_adopt_refuses_a_rule_that_was_never_tested(tmp_path, theme):
    rule = _write_rule(tmp_path, r"\bASAP\b")
    assert _adopt(rule, theme) == 1
    assert _learned(theme) == []


def test_adopt_writes_the_rule_on_probation_with_provenance(tmp_path, theme, version):
    rule = _write_rule(tmp_path, r"\bASAP\b")
    assert _test(rule, version, theme) == 0
    assert _adopt(rule, theme) == 0
    written = _learned(theme)
    assert len(written) == 1
    data = yaml.safe_load(written[0].read_text(encoding="utf-8"))
    assert data["id"] == "feedback.no-asap"
    assert data["origin"] == "feedback"
    assert data["status"] == "probation"
    provenance = json.dumps(data["provenance"], default=str)
    assert REVIEW_COPY in provenance
    assert AUTHOR in provenance
    assert COMMENT_DATE in provenance


def test_adopt_sets_origin_and_status_even_when_the_proposal_claims_otherwise(tmp_path, theme, version):
    proposal = _rule(r"\bASAP\b") | {"origin": "manual", "status": "active"}
    rule = tmp_path / "rule.yaml"
    rule.write_text(yaml.safe_dump(proposal), encoding="utf-8")
    assert _test(rule, version, theme) == 0
    assert _adopt(rule, theme) == 0
    data = yaml.safe_load(_learned(theme)[0].read_text(encoding="utf-8"))
    assert (data["origin"], data["status"]) == ("feedback", "probation")


def test_adopting_twice_leaves_one_rule(tmp_path, theme, version):
    rule = _write_rule(tmp_path, r"\bASAP\b")
    assert _test(rule, version, theme) == 0
    assert _adopt(rule, theme) == 0
    _adopt(rule, theme)
    assert len(_learned(theme)) == 1


def _findings(version: Path) -> list[dict]:
    return json.loads((version / "findings.json").read_text(encoding="utf-8"))


def _adopted_theme(tmp_path, theme, version) -> None:
    rule = _write_rule(tmp_path, r"\bASAP\b", severity="error")
    assert _test(rule, version, theme) == 0
    assert _adopt(rule, theme) == 0


def test_a_probation_rule_finds_the_text_as_a_warning_in_a_build(tmp_path, theme, version):
    _adopted_theme(tmp_path, theme, version)
    work = tmp_path / "work"
    assert main(["build", str(work / "note.md"), "--theme", str(theme)]) == 0
    latest = work / "note.versions" / "v2"
    hits = [f for f in _findings(latest) if f["rule_id"] == "feedback.no-asap"]
    assert [(f["section_id"], f["severity"]) for f in hits] == [("bad01", "warning")]
    assert json.loads((latest / "manifest.json").read_text())["findings"]["error"] == 0


def test_a_probation_finding_never_blocks_sent(tmp_path, theme, version, capsys):
    _adopted_theme(tmp_path, theme, version)
    work = tmp_path / "work"
    assert main(["build", str(work / "note.md"), "--theme", str(theme)]) == 0
    latest = work / "note.versions" / "v2"
    empty = tmp_path / "look.json"
    empty.write_text("[]")
    assert main(["look", str(latest), "--findings", str(empty)]) == 0
    assert main(["sent", str(latest), "--to", "dana@example.com"]) == 0
    assert json.loads((latest / "manifest.json").read_text())["state"] == "sent"
