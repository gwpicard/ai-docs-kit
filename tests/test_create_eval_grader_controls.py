"""Additional offline controls for the release eval's file-content graders."""

import json

import pytest

from test_create_plugin_eval import _case, _graders, _passes


def _file_graders(filename):
    return [
        grader
        for grader in _graders(_case())
        if grader.get("type") == "regex" and grader["target"]["path"].endswith(filename)
    ]


@pytest.mark.parametrize("recorded", [False, True])
def test_look_requires_agent_record_even_when_engine_is_clean(recorded):
    manifest = {"findings": {"error": 0}, "look": {"clean": True, "agent": [] if recorded else None}}
    assert _passes(_file_graders("manifest.json"), json.dumps(manifest)) is recorded


def test_cited_sections_can_have_uncited_sections_between_them():
    blocks = []
    for index in range(5):
        citation = " [S1]" if index % 2 == 0 else ""
        blocks.append(
            f'::: {{#a{index} .section intent="body"}}\n## Finding\n\nThe log was checked.{citation}\n:::\n\n'
        )
    assert _passes(_file_graders(".md"), "".join(blocks))


@pytest.mark.parametrize("body", ["[S1]", "", "## Heading with a citation [S1]"])
def test_citations_without_drafted_body_do_not_count(body):
    text = "".join(f'::: {{#a{i} .section intent="body"}}\n## Finding\n\n{body}\n:::\n\n' for i in range(3))
    assert not _passes(_file_graders(".md"), text)
