"""Source-only evidence preserves capitalised openings through section put."""

from pathlib import Path

import pytest

from ai_docs_kit.cli import main

FIXTURES = Path(__file__).parent / "fixtures" / "section-put-fact-guard"


@pytest.mark.parametrize("format", ["doc", "slides"])
@pytest.mark.parametrize("bullet", [False, True], ids=["prose", "bullet"])
@pytest.mark.parametrize(
    ("source", "claim"),
    [
        ("The EU survey was completed in 2024.", "The EU completed it."),
        (
            "The Northern Fisheries Council completed the survey in 2024.",
            "The Northern Fisheries Council completed it.",
        ),
        ("In Varnholm, the survey was completed in 2024.", "In Varnholm, the survey ended."),
    ],
)
def test_capitalised_source_openings_support_names_and_keep_refusals(tmp_path, capsys, format, bullet, source, claim):
    working = tmp_path / "report.md"
    original = (FIXTURES / "working.md").read_text(encoding="utf-8")
    original = original.replace("format: doc", f"format: {format}")
    original = original.replace("the EU survey was completed in 2024.", source)
    working.write_text(original, encoding="utf-8")
    block = tmp_path / "draft.md"
    text = f"{claim} In March 2024, the fleet was counted."
    block.write_text(
        '::: {#findings .section intent="body"}\n## Findings\n\n' + ("- " if bullet else "") + text + "\n:::\n",
        encoding="utf-8",
    )

    assert main(["section", "put", str(working), "findings", "--from", str(block)]) == 0, capsys.readouterr().err
    assert text in working.read_text(encoding="utf-8")
    before = working.read_bytes()
    capsys.readouterr()
    block.write_text(
        '::: {#findings .section intent="body"}\n## Findings\n\n'
        + ("- " if bullet else "")
        + "The Eastern Reef Agency counted 97 vessels.\n:::\n",
        encoding="utf-8",
    )

    assert main(["section", "put", str(working), "findings", "--from", str(block)]) == 1
    err = capsys.readouterr().err
    assert "fact-unsupported" in err and "(97, eastern reef agency)" in err
    assert working.read_bytes() == before


@pytest.mark.parametrize("bullet", [False, True], ids=["prose", "bullet"])
@pytest.mark.parametrize(("opening", "closing"), [("“", "”"), ("‘", "’"), ('"', '"'), ("'", "'")])
@pytest.mark.parametrize("terminal", [".", "!", "?"])
def test_quoted_ordinary_word_control_is_paired_with_a_supported_name(
    tmp_path, capsys, bullet, opening, closing, terminal
):
    working = tmp_path / "report.md"
    working.write_text((FIXTURES / "working.md").read_text(encoding="utf-8"), encoding="utf-8")
    block = tmp_path / "draft.md"
    prefix = f"the note says {opening}complete{terminal}{closing} "
    # Check the ordinary word and the remaining name after the same quoted boundary.
    text = f"{prefix}The fleet was counted. {prefix}The EU completed it."
    block.write_text(
        '::: {#findings .section intent="body"}\n## Findings\n\n' + ("- " if bullet else "") + text + "\n:::\n",
        encoding="utf-8",
    )

    assert main(["section", "put", str(working), "findings", "--from", str(block)]) == 0, capsys.readouterr().err
    assert text in working.read_text(encoding="utf-8")
