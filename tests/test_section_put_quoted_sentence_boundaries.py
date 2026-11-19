"""Check names after quoted sentences through section put (issue 278 review)."""

from pathlib import Path

import pytest

from ai_docs_kit.cli import main

FIXTURES = Path(__file__).parent / "fixtures" / "section-put-fact-guard"


@pytest.mark.parametrize("bullet", [False, True], ids=["prose", "bullet"])
@pytest.mark.parametrize(("opening", "closing"), [("“", "”"), ("‘", "’"), ('"', '"'), ("'", "'")])
@pytest.mark.parametrize("terminal", [".", "!", "?"])
@pytest.mark.parametrize(
    ("claim", "unsupported", "unlisted_eu"),
    [
        ("The EU completed it.", None, False),
        ("In March 2024, the survey ended.", None, False),
        ("The fleet was counted.", None, False),
        ("The EU completed it.", "eu", True),
        ("In Varnholm, the survey ended.", "varnholm", False),
        ("The Northern Fisheries Council reported 97 vessels.", "97, northern fisheries council", False),
        ("In March 2099, the survey ended.", "2099", False),
    ],
)
def test_sentence_openings_after_closing_quotes(
    tmp_path, capsys, bullet, opening, closing, terminal, claim, unsupported, unlisted_eu
):
    working = tmp_path / "report.md"
    original = (FIXTURES / "working.md").read_text(encoding="utf-8")
    if unlisted_eu:
        original = original.replace("the EU survey", "the regional survey")
    working.write_text(original, encoding="utf-8")
    before = working.read_bytes()
    text = f"the note says {opening}complete{terminal}{closing} {claim}"
    block = tmp_path / "draft.md"
    block.write_text(
        '::: {#findings .section intent="body"}\n## Findings\n\n' + ("- " if bullet else "") + text + "\n:::\n",
        encoding="utf-8",
    )

    code = main(["section", "put", str(working), "findings", "--from", str(block)])
    captured = capsys.readouterr()

    if unsupported is None:
        assert code == 0, captured.err
        assert text in working.read_text(encoding="utf-8")
    else:
        assert code == 1
        assert "fact-unsupported" in captured.err
        assert f"({unsupported})" in captured.err
        assert working.read_bytes() == before
