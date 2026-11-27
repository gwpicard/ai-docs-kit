"""Issue 375, including the build-side evidence omissions reported in #305 and #266.

The build entry point must consult the gathered facts store used by section put,
sources and front matter, and retain findings even for human-owned sections.
Each case has a supported control and the same document with one seeded defect.
"""

import json
from pathlib import Path

import pytest

from ai_docs_kit import cli


def _run(capsys, *args):
    capsys.readouterr()
    result = cli.main([str(arg) for arg in args])
    output = capsys.readouterr()
    return result, output.out, output.err


def _build(path, capsys):
    code, out, err = _run(capsys, "build", path)
    assert code == 0, (out, err)
    assert not err
    version = Path(out.splitlines()[-1])
    findings = json.loads((version / "findings.json").read_bytes())
    manifest = json.loads((version / "manifest.json").read_bytes())
    return out, findings, manifest


def _number_findings(findings):
    return [finding for finding in findings if finding["rule_id"] == "source.number-in-source"]


@pytest.mark.parametrize(("format_", "intent", "bullet"), [("doc", "body", False), ("slides", "bullets", True)])
@pytest.mark.parametrize("human", [False, True], ids=["ai-owned", "human-owned"])
@pytest.mark.parametrize("reverse", [False, True], ids=["defect-first", "defect-last"])
def test_build_uses_gathered_facts_sources_and_front_matter_for_every_owner(
    tmp_path, capsys, format_, intent, bullet, human, reverse
):
    path = tmp_path / "readings.md"
    owner = "human" if human else "ai"
    prefix = "- " if bullet else ""
    sections = [
        f'::: {{#gathered .section intent="{intent}" owner="{owner}"}}\n'
        f"## Reading\n\n{prefix}The reading is 12. [S1]\n:::\n",
        f'::: {{#source .section intent="{intent}"}}\n## Source reading\n\n{prefix}The count is 34. [S2]\n:::\n',
        f'::: {{#front .section intent="{intent}"}}\n## Audience\n\n{prefix}The audience has 56 people.\n:::\n',
    ]
    if reverse:
        sections.reverse()
    text = (
        f"---\nformat: {format_}\ntitle: Readings\naudience: A group of 56 people\n---\n\n"
        "## Sources\n\n- [S1] https://example.invalid/readings\n- [S2] The count is 34.\n\n" + "\n".join(sections)
    )
    path.write_text(text, encoding="utf-8")
    incoming = tmp_path / "gathered.json"
    incoming.write_text(json.dumps([{"text": "The reading is 12.", "source": "S1"}]), encoding="utf-8")
    code, out, err = _run(capsys, "facts", "add", path, incoming)
    assert code == 0, (out, err)
    store = tmp_path / ".ai_docs_kit/facts/readings.md.json"
    assert json.loads(store.read_bytes())[0]["source"] == "S1"
    assert not (tmp_path / ".ai_docs_kit/write/readings/facts.json").exists()
    facts_before = store.read_bytes()
    _, clean, _ = _build(path, capsys)
    assert _number_findings(clean) == [], "gathered facts, source descriptions and front matter are valid evidence"

    # Only the claim changes. The person's wording is not added to the evidence.
    path.write_text(text.replace("The reading is 12. [S1]", "The reading is 987. [S1]"), encoding="utf-8")
    working_before = path.read_bytes()
    out, findings, manifest = _build(path, capsys)
    unsupported = _number_findings(findings)
    assert len(unsupported) == 1, "build must report the unsupported figure using the gathered facts store"
    finding = unsupported[0]
    assert (finding["section_id"], finding["severity"], finding["tier"]) == ("gathered", "error", "source")
    assert finding["measured"]["number"] == "987"
    assert "error source.number-in-source gathered" in out
    assert manifest["findings"]["error"] >= 1 and manifest["look"]["clean"] is False
    assert path.read_bytes() == working_before and store.read_bytes() == facts_before

    # Reusing the same rendered content must still reread the gathered facts.
    incoming.write_text(json.dumps([{"text": "The reading is 987.", "source": "S1"}]), encoding="utf-8")
    code, out, err = _run(capsys, "facts", "add", path, incoming)
    assert code == 0, (out, err)
    _, supported_again, _ = _build(path, capsys)
    assert _number_findings(supported_again) == []
