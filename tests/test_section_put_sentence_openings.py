"""Judge sentence openings and citation metadata through section put (issue 278)."""

from pathlib import Path

import pytest

from ai_docs_kit.cli import main

FIXTURES = Path(__file__).parent / "fixtures" / "section-put-fact-guard"


def _seed(tmp_path, *, previous="", unlisted_eu=False):
    text = (FIXTURES / "working.md").read_text(encoding="utf-8")
    if unlisted_eu:
        text = text.replace("the EU survey", "the regional survey")
    text = text.replace("## Findings\n", f"## Findings\n\n{previous}\n")
    working = tmp_path / "report.md"
    working.write_text(text, encoding="utf-8")
    return working


def _draft(tmp_path, text, bullet=False):
    block = tmp_path / "draft.md"
    block.write_text(
        '::: {#findings .section intent="body"}\n## Findings\n\n' + ("- " if bullet else "") + text + "\n:::\n",
        encoding="utf-8",
    )
    return block


def _put(working, block):
    return main(["section", "put", str(working), "findings", "--from", str(block)])


@pytest.mark.parametrize("kind", ["pass", "fail"])
def test_seeded_fixture_pair_checks_names_and_numbers(tmp_path, capsys, kind):
    working = _seed(tmp_path)
    before = working.read_text(encoding="utf-8")
    block = FIXTURES / f"{kind}.md"

    code = _put(working, block)
    captured = capsys.readouterr()

    if kind == "pass":
        assert code == 0, captured.err
        accepted = working.read_text(encoding="utf-8")
        assert "The EU completed the survey." in accepted
        assert "In March 2024, the fleet was counted." in accepted
        assert "[S3 p.6-7]" in accepted
        assert "[S1, p. 12]" in accepted
    else:
        assert code == 1, captured
        assert "fact-unsupported" in captured.err
        assert "northern fisheries council" in captured.err.lower()
        assert "97" in captured.err
        assert working.read_text(encoding="utf-8") == before


@pytest.mark.parametrize("bullet", [False, True], ids=["prose", "bullet"])
@pytest.mark.parametrize(
    "text",
    [
        "The EU completed the survey.",
        "In March 2024, the fleet was counted.",
        "The EU completed the survey. In March 2024, the fleet was counted.",
        "In March 2024, the fleet was counted. The EU completed the survey.",
    ],
)
def test_supported_sentence_openings_are_accepted(tmp_path, capsys, bullet, text):
    working = _seed(tmp_path)

    assert _put(working, _draft(tmp_path, text, bullet)) == 0, capsys.readouterr().err
    assert text in working.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("text", "token"),
    [
        ("The EU completed the survey.", "eu"),
        ("In Varnholm, the survey was completed.", "varnholm"),
    ],
)
def test_name_after_sentence_opening_is_checked_on_its_own(tmp_path, capsys, text, token):
    working = _seed(tmp_path, unlisted_eu=True)
    before = working.read_text(encoding="utf-8")

    assert _put(working, _draft(tmp_path, text)) == 1
    err = capsys.readouterr().err.lower()
    assert "fact-unsupported" in err
    assert f"({token})" in err, "the unsupported token must be the name alone"
    assert working.read_text(encoding="utf-8") == before


@pytest.mark.parametrize("bullet", [False, True], ids=["prose", "bullet"])
@pytest.mark.parametrize("citation", ["[S3 p.6-7]", "[S1, p. 12]", "[S3, p. 6-7]"])
@pytest.mark.parametrize("citation_first", [False, True], ids=["trailing", "leading"])
def test_citation_numbers_are_not_claims(tmp_path, capsys, bullet, citation, citation_first):
    working = _seed(tmp_path)
    claim = "the survey was completed in 2024."
    text = f"{citation} {claim}" if citation_first else f"{claim} {citation}"

    assert _put(working, _draft(tmp_path, text, bullet)) == 0, capsys.readouterr().err
    accepted = working.read_text(encoding="utf-8")
    assert claim in accepted
    assert citation.replace(",", "") in accepted.replace(",", "")


@pytest.mark.parametrize("citation", ["[S1, p. 12]", "[S3, p. 6-7]"])
def test_citation_numbers_in_old_text_do_not_support_new_claims(tmp_path, capsys, citation):
    number = "12" if "12" in citation else "7"
    working = _seed(tmp_path, previous=f"the survey was completed. {citation}")
    before = working.read_text(encoding="utf-8")
    block = _draft(tmp_path, f"the survey covered {number} sites. [S1]")

    assert _put(working, block) == 1
    err = capsys.readouterr().err
    assert "fact-unsupported" in err and number in err
    assert working.read_text(encoding="utf-8") == before


def test_comma_citation_still_checks_its_source_key(tmp_path, capsys):
    working = _seed(tmp_path)
    before = working.read_text(encoding="utf-8")
    block = _draft(tmp_path, "the survey was completed in 2024. [S99, p. 2024]")

    assert _put(working, block) == 1
    err = capsys.readouterr().err
    assert "fact-unsupported" in err and "cite:S99" in err
    assert working.read_text(encoding="utf-8") == before
