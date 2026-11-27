"""Human prose keeps citation metadata separate from the figures it claims."""

import json

import pytest

from ai_docs_kit import api, cli
from ai_docs_kit.model import Section


def _working(tmp_path):
    path = tmp_path / "readings.md"
    path.write_text(
        "---\nformat: doc\ntitle: Readings\n---\n\n"
        "## Sources\n\n- [S1] https://example.invalid/readings\n- [S2] https://example.invalid/other\n\n"
        '::: {#reading .section intent="body"}\n## Reading\n\nThe scope is agreed.\n:::\n',
        encoding="utf-8",
    )
    incoming = tmp_path / "facts.json"
    incoming.write_text(
        json.dumps(
            [
                {"text": "The reading is 12. [S1 p.987]", "source": "S1", "locator": "p.4"},
                {"text": "The reading is 34.", "source": "S1", "locator": "p.5"},
                {"text": "The reading is 987.", "source": "S2"},
            ]
        ),
        encoding="utf-8",
    )
    assert cli.main(["facts", "add", str(path), str(incoming)]) == 0
    return path


def test_human_paragraphs_use_their_cited_source_and_locator(tmp_path):
    path = _working(tmp_path)
    paragraphs = [
        "The reading is 12. [S1 p.4]",
        "The reading is 34. [S1 p.5]",
        "The reading is 34. [S1 p.4]",
        "The reading is 987. [S1 p.987]",
        "The reading is 987. [S2]",
    ]
    api.edit_fields(path, "reading", {"paragraphs": paragraphs}, 0)
    findings = [finding for finding in api.build(path).findings if finding.rule_id == "source.number-in-source"]
    assert [(finding.measured["field"], finding.measured["number"]) for finding in findings] == [
        ("paragraphs[2]", "34"),
        ("paragraphs[3]", "987"),
    ]
    assert api.read_document(path).sections[0].paragraphs == paragraphs


def test_human_edit_is_checked_before_any_facts_are_gathered(tmp_path):
    path = tmp_path / "readings.md"
    path.write_text(
        "---\nformat: doc\naudience: A group of 56 people\n---\n\n"
        "## Sources\n\n- [S1] The reading is 12.\n\n"
        '::: {#reading .section intent="body"}\n## Reading\n\nThe scope is agreed.\n:::\n',
        encoding="utf-8",
    )
    api.edit_fields(
        path,
        "reading",
        {"paragraphs": ["The reading is 12. [S1]", "The audience has 56 people.", "The reading is 987. [S1]"]},
        0,
    )
    findings = [finding for finding in api.build(path).findings if finding.rule_id == "source.number-in-source"]
    assert [(finding.section_id, finding.measured["number"]) for finding in findings] == [("reading", "987")]


@pytest.mark.parametrize("existing", ["", '::: {.section intent="body"}\n\nOriginal wording.\n:::\n'])
def test_prepend_returns_the_inserted_section_with_no_existing_ids(tmp_path, existing):
    path = tmp_path / "readings.md"
    path.write_text("---\nformat: doc\n---\n\n" + existing, encoding="utf-8")
    before = api.read_document(path)
    result = api.add_section(path, None, Section(intent="body", paragraphs=["Added wording."]), 0)
    after = api.read_document(path)
    assert result.rev == after.rev == 1
    assert result.section == after.sections[0]
    assert result.section.id and result.section.paragraphs == ["Added wording."]
    assert after.sections[1:] == before.sections


@pytest.mark.parametrize("command", ["build", "check"])
def test_corrupt_gathered_evidence_is_refused_without_saving_a_version(tmp_path, capsys, command):
    path = _working(tmp_path)
    capsys.readouterr()
    store = tmp_path / ".ai_docs_kit" / "facts" / "readings.md.json"
    store.write_bytes(b"[{}]")
    before = path.read_bytes()
    assert cli.main([command, str(path)]) == 2
    output = capsys.readouterr()
    assert str(store) in output.err and "cannot read facts" in output.err
    assert len(output.err.splitlines()) == 1
    assert path.read_bytes() == before
    assert not path.with_suffix(".versions").exists()
