"""Rule examples preserve section ids that resemble relative or absolute paths."""

import json

import pytest
import yaml

from ai_docs_kit.cli import main


@pytest.mark.parametrize("target", ["./timing", "/timing", "part/timing/"])
@pytest.mark.parametrize("reverse", [False, True], ids=["forward", "reversed"])
@pytest.mark.parametrize(("fmt", "intent"), [("doc", "body"), ("slides", "statement")])
def test_rule_test_preserves_literal_section_ids(tmp_path, capsys, target, reverse, fmt, intent):
    section_ids = ["timing", "part/timing", target]
    if reverse:
        section_ids.reverse()
    blocks = []
    for index, section_id in enumerate(section_ids):
        wording = (
            "Please reply ASAP about the meeting." if section_id == target else f"Discuss topic {index} by Friday."
        )
        blocks.append(f'::: {{#{section_id} .section intent="{intent}"}}\n## Timing\n\n{wording}\n:::\n')
    source = tmp_path / "note.md"
    source.write_text(
        f"---\ndoctype: report\nformat: {fmt}\ntitle: Timing\n---\n\n" + "\n".join(blocks),
        encoding="utf-8",
    )
    assert main(["build", str(source)]) == 0
    version = tmp_path / "note.versions" / "v1"
    composition = json.loads((version / "composition.json").read_text(encoding="utf-8"))
    assert [section["id"] for section in composition["sections"]] == section_ids
    rule = {
        "id": "feedback.give-date",
        "title": "Give a date",
        "origin": "feedback",
        "strength": "soft",
        "status": "proposed",
        "severity": "error",
        "tier": "source",
        "check": {"kind": "text-pattern", "field": "paragraphs", "regex": "ASAP"},
        "remedy": {"class": "redraft", "hint": "Give a date."},
        "provenance": {"label": "answered", "source": {"comment": "Give a date."}, "by": "Dana"},
    }
    path = tmp_path / "rule.yaml"
    path.write_text(yaml.safe_dump(rule), encoding="utf-8")
    capsys.readouterr()

    code = main(["rule", "test", str(path), "--example", f"{version}/{target}"])
    output = capsys.readouterr()
    assert code == 0, output.err
    assert f"fires on v1/{target} and on no approved exemplar" in output.out
    assert not output.err

    for section_id in section_ids:
        if section_id == target:
            continue
        code = main(["rule", "test", str(path), "--example", f"{version}/{section_id}"])
        output = capsys.readouterr()
        assert code == 1, output.err
        assert f"misses the example v1/{section_id}" in output.out
        assert not output.err

    assert main(["rule", "test", str(path), "--example", f"{version}/"]) == 2
    assert "--example must be <version folder>/<section id>" in capsys.readouterr().err
