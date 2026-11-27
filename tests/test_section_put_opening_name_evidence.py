"""Check opening names against gathered facts through section put."""

import json
from pathlib import Path

import pytest

from ai_docs_kit.cli import main

FIXTURES = Path(__file__).parent / "fixtures" / "section-put-fact-guard"


@pytest.mark.parametrize("bullet", [False, True], ids=["prose", "bullet"])
@pytest.mark.parametrize(
    ("fact", "claim", "token"),
    [
        ("EU completed the survey.", "The EU completed the survey.", None),
        ("Varnholm completed the survey.", "In Varnholm, the survey was completed.", None),
        ("Northern Fisheries Council completed it.", "The Northern Fisheries Council completed it.", None),
        ("the survey was completed.", "[S1, p. 12] The EU completed it.", "eu"),
        ("the survey was completed.", "the survey ended! In Varnholm, it resumed.", "varnholm"),
        (
            "the survey was completed.",
            "the survey ended? The Northern Fisheries Council resumed it.",
            "northern fisheries council",
        ),
        ("the survey was completed.", "In March 2099, the survey was completed.", "2099"),
    ],
)
def test_opening_names_use_evidence_without_weakening_refusals(tmp_path, capsys, bullet, fact, claim, token):
    working = tmp_path / "report.md"
    working.write_text(
        (FIXTURES / "working.md")
        .read_text(encoding="utf-8")
        .replace("the EU survey", "the regional survey")
        .replace("- [S1] ", "- [S1] survey.md, "),
        encoding="utf-8",
    )
    (tmp_path / "survey.md").write_text(fact, encoding="utf-8")
    facts = tmp_path / "facts.json"
    facts.write_text(json.dumps([{"text": fact, "source": "S1"}]), encoding="utf-8")
    assert main(["facts", "add", str(working), str(facts)]) == 0
    capsys.readouterr()
    block = tmp_path / "draft.md"
    block.write_text(
        '::: {#findings .section intent="body"}\n## Findings\n\n' + ("- " if bullet else "") + claim + "\n:::\n",
        encoding="utf-8",
    )
    before = working.read_bytes()

    code = main(["section", "put", str(working), "findings", "--from", str(block)])
    captured = capsys.readouterr()

    if token is None:
        assert code == 0, captured.err
        assert claim in working.read_text(encoding="utf-8")
    else:
        assert code == 1
        assert "fact-unsupported" in captured.err
        assert f"({token})" in captured.err
        assert working.read_bytes() == before
