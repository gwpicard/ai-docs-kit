"""Judge bold-head boundaries and working-file counts through section put."""

import pytest

from ai_docs_kit.cli import main


def _working(folder, format, sources, section_count, *, target_first=True):
    folder.mkdir()
    working = folder / "report.md"
    sections = ['::: {#findings .section intent="body"}\n## Findings\n:::']
    sections.extend(
        f'::: {{#background-{index} .section intent="body"}}\n## Background\n:::' for index in range(section_count - 1)
    )
    if not target_first:
        sections.reverse()
        sources = list(reversed(sources))
    working.write_text(
        f"---\ndoctype: report\nformat: {format}\ntitle: Survey note\n---\n\n## Sources\n\n"
        + "\n".join(sources)
        + "\n\n"
        + "\n\n".join(sections)
        + "\n",
        encoding="utf-8",
    )
    return working


def _put(working, lines, *, bullet):
    block = working.parent / "draft.md"
    block.write_text(
        '::: {#findings .section intent="body"}\n## Findings\n\n'
        + "\n\n".join(("- " if bullet else "") + line for line in lines)
        + "\n:::\n",
        encoding="utf-8",
    )
    return main(["section", "put", str(working), "findings", "--from", str(block)])


@pytest.mark.parametrize("format", ["doc", "slides"])
@pytest.mark.parametrize("ordinary_first", [True, False], ids=["ordinary-first", "name-first"])
@pytest.mark.parametrize(
    ("templates", "ordinary"),
    [
        (("**Option A: {claim}**",), "Extend as proposed."),
        (("**Eastfield:** {claim}",), "Keep the zone"),
        (("**Eastfield**: {claim}",), "Keep the zone"),
        (("**Eastfield**. {claim}", "**Eastfield.** {claim}"), "Keep the zone"),
    ],
    ids=["whole-bold-option", "colon-inside", "colon-outside", "full-stops"],
)
def test_bold_heads_accept_ordinary_words_and_supported_names_but_refuse_new_names(
    tmp_path, capsys, format, ordinary_first, templates, ordinary
):
    sources = [
        "- [S1] the proposal is labelled Option A and the zone is labelled Eastfield.",
        "- [S2] The Northern Fisheries Council reviewed the proposal.",
    ]
    # Pair the already supported outside full stop with the missing inside boundary.
    for index, template in enumerate(templates):
        # Lists can split a head from its body; prose must exercise the shared boundary too.
        for bullet in (True, False):
            folder = tmp_path / f"{index}-{'items' if bullet else 'prose'}"
            working = _working(folder, format, sources, 1)
            before = working.read_bytes()
            for claim, token in [
                ("Eastern Reef Agency reviewed the proposal.", "eastern reef agency"),
                ("In Varnholm, the zone was reviewed.", "varnholm"),
            ]:
                assert _put(working, [template.format(claim=claim)], bullet=bullet) == 1
                err = capsys.readouterr().err
                assert "fact-unsupported" in err and token in err.lower(), err
                assert working.read_bytes() == before

            lines = [
                template.format(claim=ordinary),
                template.format(claim="The Northern Fisheries Council reviewed the proposal."),
            ]
            if not ordinary_first:
                lines.reverse()
            code = _put(working, lines, bullet=bullet)
            captured = capsys.readouterr()
            assert code == 0, captured.err
            assert working.read_bytes() != before
            written = working.read_text(encoding="utf-8")
            for line in lines:
                assert ("- " if bullet else "") + line in written


@pytest.mark.parametrize("format", ["doc", "slides"])
@pytest.mark.parametrize("bullet", [False, True], ids=["prose", "items"])
@pytest.mark.parametrize("count_first", [True, False], ids=["count-first", "count-last"])
@pytest.mark.parametrize(
    ("noun", "word", "source_count", "section_count", "wrong_word", "wrong_token"),
    [
        ("source", "one", 1, 3, "two", "2"),
        ("sources", "four", 4, 2, "five", "5"),
        ("section", "one", 3, 1, "two", "2"),
        ("sections", "four", 2, 4, "five", "5"),
    ],
    ids=["source", "sources", "section", "sections"],
)
def test_working_file_counts_are_local_to_source_and_section_phrases(
    tmp_path, capsys, format, bullet, count_first, noun, word, source_count, section_count, wrong_word, wrong_token
):
    sources = [f"- [S{index}] the survey was reviewed." for index in range(1, source_count + 1)]
    working = _working(tmp_path / "project", format, sources, section_count, target_first=count_first)
    before = working.read_bytes()
    accepted = f"the working file lists {word} {noun}."
    plural = noun if noun.endswith("s") else noun + "s"
    vessels = "vessel" if word == "one" else "vessels"
    # Check defects before accepting the count, so previous text supplies no figures.
    for defect, token in [
        (f"the working file lists {wrong_word} {plural}.", wrong_token),
        (f"the crew used {word} {vessels}.", "1" if word == "one" else "4"),
    ]:
        lines = [accepted, defect] if count_first else [defect, accepted]
        assert _put(working, lines, bullet=bullet) == 1
        err = capsys.readouterr().err
        assert "fact-unsupported" in err, err
        assert token in err.partition("(")[2], err
        assert working.read_bytes() == before

    code = _put(working, [accepted], bullet=bullet)
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert working.read_bytes() != before
    assert ("- " if bullet else "") + accepted in working.read_text(encoding="utf-8")
