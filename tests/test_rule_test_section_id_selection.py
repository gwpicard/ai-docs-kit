"""Rule examples select complete section ids regardless of depth or source order."""

import json

import pytest
import yaml

from ai_docs_kit.cli import main


@pytest.mark.parametrize("target", ["part/timing", "part/sub/timing"])
@pytest.mark.parametrize("reverse", [False, True], ids=["forward", "reversed"])
def test_rule_test_selects_the_full_id_among_sections_with_the_same_suffix(tmp_path, capsys, target, reverse):
    section_ids = ["timing", "part/timing", "part/sub/timing"]
    if reverse:
        section_ids.reverse()
    blocks = []
    for section_id in section_ids:
        wording = "Please reply ASAP." if section_id == target else "Please reply by Friday."
        blocks.append(f'::: {{#{section_id} .section intent="body"}}\n## Timing\n\n{wording}\n:::\n')
    source = tmp_path / "note.md"
    source.write_text(
        "---\ndoctype: report\nformat: doc\ntitle: Timing\n---\n\n" + "\n".join(blocks),
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
