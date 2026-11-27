"""Section drafting checks claims separately from citation keys and locators."""

import json

import pytest

from ai_docs_kit.cli import main
from ai_docs_kit.render.typst import compile_pdf
from ai_docs_kit.theme import neutral_theme

CLAIM = "The fleet counted 5,232 vessels."


def _seed(tmp_path, format, locator="p.2"):
    if locator == "00:41":
        source_name = "fleet-register.vtt"
        (tmp_path / source_name).write_text(
            "WEBVTT\n\n00:00:41.000 --> 00:00:45.000\n" + CLAIM + "\n", encoding="utf-8"
        )
    else:
        source_name = "fleet-register.pdf"
        source = tmp_path / "fleet-register.typ"
        source.write_text("The survey was completed.\n#pagebreak()\n" + CLAIM, encoding="utf-8")
        compile_pdf(source, tmp_path, tmp_path / source_name, [neutral_theme().fonts_dir])
    working = tmp_path / "report.md"
    working.write_text(
        f"---\ndoctype: report\nformat: {format}\ntitle: Fleet note\n---\n\n"
        f"## Sources\n\n- [S1] {source_name}, fleet register\n\n"
        '::: {#findings .section intent="body"}\n## Findings\n:::\n',
        encoding="utf-8",
    )
    return working


def _block(tmp_path, text, bullet):
    block = tmp_path / "draft.md"
    block.write_text(
        '::: {#findings .section intent="body"}\n## Findings\n\n' + ("- " if bullet else "") + text + "\n:::\n",
        encoding="utf-8",
    )
    return block


def _put(working, block):
    return main(["section", "put", str(working), "findings", "--from", str(block)])


def _add(tmp_path, working, locator):
    incoming = tmp_path / "facts.json"
    incoming.write_text(json.dumps([{"text": CLAIM, "source": "S1", "locator": locator}]), encoding="utf-8")
    assert main(["facts", "add", str(working), str(incoming)]) == 0


@pytest.mark.parametrize("format", ["doc", "slides"])
@pytest.mark.parametrize("bullet", [False, True], ids=["prose", "bullet"])
@pytest.mark.parametrize("locator", ["p.2", "00:41"])
def test_stored_claim_with_locator_is_accepted_but_a_new_number_is_refused(tmp_path, capsys, format, bullet, locator):
    working = _seed(tmp_path, format, locator)
    _add(tmp_path, working, locator)
    capsys.readouterr()
    block = _block(tmp_path, f"{CLAIM} [S1 {locator}]", bullet)

    assert _put(working, block) == 0, capsys.readouterr().err
    accepted = working.read_text(encoding="utf-8")
    assert f"[S1 {locator}]" in accepted
    capsys.readouterr()
    block = _block(tmp_path, f"{CLAIM.replace('5,232', '9,876')} [S1 {locator}]", bullet)

    assert _put(working, block) == 1
    err = capsys.readouterr().err
    assert "fact-unsupported" in err and "9876" in err
    assert working.read_text(encoding="utf-8") == accepted


@pytest.mark.parametrize("format", ["doc", "slides"])
@pytest.mark.parametrize("bullet", [False, True], ids=["prose", "bullet"])
@pytest.mark.parametrize("suffix", ["", " p.87", " 00:41"])
def test_unknown_citation_keys_are_refused_even_when_the_claim_is_supported(tmp_path, capsys, format, bullet, suffix):
    working = _seed(tmp_path, format)
    _add(tmp_path, working, "p.2")
    capsys.readouterr()
    before = working.read_text(encoding="utf-8")
    block = _block(tmp_path, f"{CLAIM} [S99{suffix}]", bullet)

    assert _put(working, block) == 1
    err = capsys.readouterr().err
    assert "fact-unsupported" in err and "cite:S99" in err
    assert working.read_text(encoding="utf-8") == before


@pytest.mark.parametrize(("locator", "number"), [("p.87", "8"), ("00:41", "41")])
def test_old_prose_locator_does_not_support_a_new_claim_number(tmp_path, capsys, locator, number):
    working = _seed(tmp_path, "doc")
    original = working.read_text(encoding="utf-8").replace("## Findings\n", f"## Findings\n\n{CLAIM} [S1 {locator}]\n")
    working.write_text(original, encoding="utf-8")
    block = _block(tmp_path, f"{CLAIM.replace('5,232', number)} [S1]", False)

    assert _put(working, block) == 1
    err = capsys.readouterr().err
    assert "fact-unsupported" in err and number in err
    assert working.read_text(encoding="utf-8") == original
