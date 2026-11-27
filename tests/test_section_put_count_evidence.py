"""Accepted working-file counts cannot support unrelated figures on later writes."""

import pytest

from ai_docs_kit.cli import main


@pytest.mark.parametrize("format", ["doc", "slides"])
@pytest.mark.parametrize("bullet", [False, True], ids=["prose", "items"])
@pytest.mark.parametrize(("noun", "word", "digit"), [("sources", "four", "4"), ("sections", "three", "3")])
def test_count_acceptance_does_not_supply_evidence_for_other_figures(
    tmp_path, capsys, format, bullet, noun, word, digit
):
    working = tmp_path / "report.md"
    working.write_text(
        f"---\ndoctype: report\nformat: {format}\n---\n\n## Sources\n\n"
        + "\n".join(f"- [S{index}] the survey was reviewed." for index in range(1, 5))
        + '\n\n::: {#findings .section intent="body"}\n## Findings\n:::\n'
        + '\n::: {#background .section intent="body"}\n## Background\n:::\n'
        + '\n::: {#conclusion .section intent="body"}\n## Conclusion\n:::\n',
        encoding="utf-8",
    )
    draft = tmp_path / "draft.md"
    accepted = f"the working file lists {word} {noun}."
    before = working.read_bytes()
    for figure in (None, word, digit):
        text = accepted + (f" the crew used {figure} vessels." if figure is not None else "")
        draft.write_text(
            '::: {#findings .section intent="body"}\n## Findings\n\n'
            + ("- **Summary** " if bullet else "")
            + text
            + "\n:::\n",
            encoding="utf-8",
        )
        code = main(["section", "put", str(working), "findings", "--from", str(draft)])
        captured = capsys.readouterr()
        if figure is None:
            assert code == 0, captured.err
            assert working.read_bytes() != before
            assert accepted in working.read_text(encoding="utf-8")
            before = working.read_bytes()
        else:
            assert code == 1, captured
            assert "fact-unsupported" in captured.err and f"({digit})" in captured.err
            assert working.read_bytes() == before
