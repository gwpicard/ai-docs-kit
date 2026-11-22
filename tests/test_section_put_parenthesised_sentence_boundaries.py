"""Check sentence boundaries after parentheses through section put."""

from pathlib import Path

import pytest

from ai_docs_kit.cli import main

FIXTURES = Path(__file__).parent / "fixtures" / "section-put-fact-guard"


@pytest.mark.parametrize("format", ["doc", "slides"])
@pytest.mark.parametrize("bullet", [False, True], ids=["prose", "bullet"])
@pytest.mark.parametrize("terminal", [".", "?", "!"])
@pytest.mark.parametrize("claim", ["The EU completed it.", "In March 2024, the fleet was counted."])
def test_parenthesised_sentence_boundary_keeps_name_and_number_checks(
    tmp_path, capsys, format, bullet, terminal, claim
):
    working = tmp_path / "report.md"
    original = (FIXTURES / "working.md").read_text(encoding="utf-8")
    working.write_text(original.replace("format: doc", f"format: {format}"), encoding="utf-8")
    block = tmp_path / "draft.md"
    prefix = f"the survey ended. (the count was complete{terminal}) "

    def put(text):
        block.write_text(
            '::: {#findings .section intent="body"}\n## Findings\n\n'
            + ("- " if bullet else "")
            + prefix
            + text
            + "\n:::\n",
            encoding="utf-8",
        )
        return main(["section", "put", str(working), "findings", "--from", str(block)])

    assert put(claim) == 0, capsys.readouterr().err
    assert prefix + claim in working.read_text(encoding="utf-8")
    capsys.readouterr()
    before = working.read_bytes()
    for unsupported_claim, token in [
        ("In Varnholm, the survey ended.", "varnholm"),
        ("The Northern Fisheries Council completed it.", "northern fisheries council"),
        ("In March 2099, the fleet counted 97 vessels.", "2099, 97"),
    ]:
        assert put(unsupported_claim) == 1
        err = capsys.readouterr().err
        assert "fact-unsupported" in err and f"({token})" in err
        assert working.read_bytes() == before
