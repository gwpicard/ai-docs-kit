"""`ai-docs-kit section get|put|list`: read and replace one section through the patch guards."""

from pathlib import Path

import pytest

from ai_docs_kit.cli import main

WORKING = """---
doctype: report
format: doc
title: Quarterly note
---

## Sources

- [S1] Revenue was 120 in 2024 and 150 in 2025.
- [S2] The audit finished in March 2025.

::: {#intro .section intent="opening" owner="ai" redraft="shorten this"}
## Introduction

Revenue grew from 120 to 150.
:::

::: {#findings .section intent="evidence"}
## Findings

- **Growth** Revenue reached 150 in 2025. [S1]
- **Audit** The audit finished in March 2025. [S2]
:::

::: {#voice .section intent="quote" owner="human"}
## Voice

A sentence a person wrote.
:::

::: {#frozen .section intent="terms" lock="text"}
## Terms

Fixed wording.
:::

::: {#sealed .section intent="legal" lock="all"}
## Legal

Sealed wording.
:::
"""


def _seed(tmp_path: Path) -> Path:
    path = tmp_path / "note.md"
    path.write_text(WORKING)
    return path


def _replacement(tmp_path: Path, block: str) -> Path:
    path = tmp_path / "new.md"
    path.write_text(block)
    return path


def _put(path: Path, section_id: str, source: Path, *extra: str) -> int:
    return main(["section", "put", str(path), section_id, "--from", str(source), *extra])


def test_list_prints_id_intent_owner_and_redraft(tmp_path, capsys):
    assert main(["section", "list", str(_seed(tmp_path))]) == 0
    lines = {line.split()[0]: line for line in capsys.readouterr().out.splitlines() if line.strip()}
    assert set(lines) == {"intro", "findings", "voice", "frozen", "sealed"}
    assert "opening" in lines["intro"] and "ai" in lines["intro"] and "shorten this" in lines["intro"]
    assert "human" in lines["voice"]
    assert "redraft" not in lines["findings"]


def test_get_prints_the_section_with_its_citations_resolved(tmp_path, capsys):
    assert main(["section", "get", str(_seed(tmp_path)), "findings"]) == 0
    out = capsys.readouterr().out
    assert "Revenue reached 150 in 2025." in out
    assert "Voice" not in out
    head, _, sources = out.partition("## Sources")
    assert sources, "get must print a ## Sources heading"
    assert "[S1] Revenue was 120 in 2024 and 150 in 2025." in sources
    assert "[S2] The audit finished in March 2025." in sources


def test_get_lists_only_the_sources_the_section_cites(tmp_path, capsys):
    assert main(["section", "get", str(_seed(tmp_path)), "intro"]) == 0
    assert "[S1]" not in capsys.readouterr().out


def test_put_replaces_only_that_section(tmp_path):
    path = _seed(tmp_path)
    block = (
        '::: {#findings .section intent="evidence"}\n## Findings\n\n'
        "- **Growth** Revenue reached 150 in 2025, up from 120. [S1]\n:::\n"
    )
    assert _put(path, "findings", _replacement(tmp_path, block)) == 0
    text = path.read_text()
    assert "up from 120" in text
    assert "The audit finished in March 2025. [S2]" not in text
    assert "#findings" in text
    assert "A sentence a person wrote." in text
    assert "Sealed wording." in text
    assert text.count(".section") == 5


def test_put_without_the_flag_keeps_the_redraft_ask(tmp_path):
    path = _seed(tmp_path)
    block = (
        '::: {#intro .section intent="opening" owner="ai" redraft="shorten this"}\n'
        "## Introduction\n\nRevenue grew.\n:::\n"
    )
    assert _put(path, "intro", _replacement(tmp_path, block)) == 0
    assert 'redraft="shorten this"' in path.read_text()


def test_put_redraft_done_removes_the_ask_and_sets_because(tmp_path):
    path = _seed(tmp_path)
    block = (
        '::: {#intro .section intent="opening" owner="ai" redraft="shorten this" because="Cut to one sentence."}\n'
        "## Introduction\n\nRevenue grew from 120 to 150.\n:::\n"
    )
    assert _put(path, "intro", _replacement(tmp_path, block), "--redraft-done") == 0
    text = path.read_text()
    assert "redraft=" not in text
    assert 'because="Cut to one sentence."' in text


@pytest.mark.parametrize(
    ("section_id", "reason"),
    [("voice", "human"), ("frozen", "locked"), ("sealed", "locked")],
)
def test_put_refuses_a_human_or_locked_section_and_says_why(tmp_path, capsys, section_id, reason):
    path = _seed(tmp_path)
    block = f'::: {{#{section_id} .section intent="x"}}\n## New\n\nReplacement text.\n:::\n'
    block = block.replace(
        'intent="x"', {"voice": 'intent="quote"', "frozen": 'intent="terms"', "sealed": 'intent="legal"'}[section_id]
    )
    before = path.read_text()
    assert _put(path, section_id, _replacement(tmp_path, block)) == 1
    assert reason in capsys.readouterr().err
    assert path.read_text() == before


def test_put_refuses_a_section_marked_human_even_with_redraft_done(tmp_path, capsys):
    path = _seed(tmp_path)
    block = '::: {#voice .section intent="quote" owner="human" because="Reworded."}\n## Voice\n\nOther.\n:::\n'
    before = path.read_text()
    assert _put(path, "voice", _replacement(tmp_path, block), "--redraft-done") == 1
    assert "human" in capsys.readouterr().err
    assert path.read_text() == before


def test_put_refuses_a_new_figure_outside_sources(tmp_path, capsys):
    path = _seed(tmp_path)
    block = (
        '::: {#findings .section intent="evidence"}\n## Findings\n\n'
        "- **Growth** Revenue reached 999 in 2025. [S1]\n:::\n"
    )
    before = path.read_text()
    assert _put(path, "findings", _replacement(tmp_path, block)) == 1
    err = capsys.readouterr().err
    assert "fact-unsupported" in err and "999" in err
    assert path.read_text() == before


def test_put_refuses_a_citation_to_an_unknown_source(tmp_path, capsys):
    path = _seed(tmp_path)
    block = (
        '::: {#findings .section intent="evidence"}\n## Findings\n\n'
        "- **Growth** Revenue reached 150 in 2025. [S9]\n:::\n"
    )
    before = path.read_text()
    assert _put(path, "findings", _replacement(tmp_path, block)) == 1
    assert "S9" in capsys.readouterr().err
    assert path.read_text() == before


def test_put_refuses_a_changed_id_or_intent(tmp_path, capsys):
    path = _seed(tmp_path)
    before = path.read_text()
    renamed = '::: {#other .section intent="evidence"}\n## Findings\n\nRevenue reached 150.\n:::\n'
    assert _put(path, "findings", _replacement(tmp_path, renamed)) == 1
    assert "identity-changed" in capsys.readouterr().err
    reintent = '::: {#findings .section intent="summary"}\n## Findings\n\nRevenue reached 150.\n:::\n'
    assert _put(path, "findings", _replacement(tmp_path, reintent)) == 1
    assert "identity-changed" in capsys.readouterr().err
    assert path.read_text() == before


@pytest.mark.parametrize("command", ["get", "put"])
def test_unknown_section_id_exits_one_and_names_it(tmp_path, capsys, command):
    path = _seed(tmp_path)
    block = _replacement(tmp_path, '::: {#nope .section intent="x"}\n## X\n\nText.\n:::\n')
    argv = ["section", command, str(path), "nope"] + (["--from", str(block)] if command == "put" else [])
    assert main(argv) == 1
    assert "nope" in capsys.readouterr().err


def test_put_with_a_missing_from_file_exits_two_and_leaves_the_file(tmp_path, capsys):
    path = _seed(tmp_path)
    before = path.read_text()
    assert _put(path, "findings", tmp_path / "absent.md") == 2
    assert "absent.md" in capsys.readouterr().err
    assert path.read_text() == before


@pytest.mark.parametrize("command", ["list", "get", "put"])
def test_missing_working_file_exits_two(tmp_path, capsys, command):
    missing = tmp_path / "nope.md"
    argv = ["section", command, str(missing)] + ([] if command == "list" else ["findings"])
    if command == "put":
        argv += ["--from", str(missing)]
    assert main(argv) == 2
    assert "nope.md" in capsys.readouterr().err
