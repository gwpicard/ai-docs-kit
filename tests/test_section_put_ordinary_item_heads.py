"""Parsed ordinary heads keep sentence openings without hiding unsupported names."""

import pytest

from ai_docs_kit.cli import main


@pytest.mark.parametrize("format", ["doc", "slides"])
@pytest.mark.parametrize("head", ["Summary", "In March"])
def test_ordinary_item_heads_preserve_openings_and_name_refusals(tmp_path, capsys, format, head):
    working = tmp_path / "report.md"
    working.write_text(
        f"---\ndoctype: report\nformat: {format}\n---\n\n## Sources\n\n"
        "- [S1] The Northern Fisheries Council reviewed the zone in Varnholm.\n\n"
        '::: {#findings .section intent="body"}\n## Findings\n:::\n',
        encoding="utf-8",
    )
    draft = tmp_path / "draft.md"
    before = working.read_bytes()
    defects = [
        (f"**{head}:** Eastern Reef Agency reviewed the zone.", "eastern reef agency"),
        (f"**{head}:** In Esterholm, the zone was reviewed.", "esterholm"),
        ("**The Eastern Reef Agency:** Keep the zone", "eastern reef agency"),
        ("**In Esterholm:** Keep the zone", "esterholm"),
        (f"**{head}:** the crew used 97 vessels.", "97"),
    ]
    ordinary = f"**{head}:** Keep the zone"
    supported = [
        ordinary,
        f"**{head}:** The Northern Fisheries Council reviewed the zone.",
        "**The Northern Fisheries Council:** Keep the zone",
        "**In Varnholm:** Keep the zone",
    ]
    for lines, token in [*(([line], token) for line, token in defects), (supported, None)]:
        draft.write_text(
            '::: {#findings .section intent="body"}\n## Findings\n\n'
            + "\n".join(f"- {line}" for line in lines)
            + "\n:::\n",
            encoding="utf-8",
        )
        code = main(["section", "put", str(working), "findings", "--from", str(draft)])
        captured = capsys.readouterr()
        if token is not None:
            assert code == 1, captured
            assert "fact-unsupported" in captured.err and f"({token})" in captured.err
            assert working.read_bytes() == before
        else:
            assert code == 0, captured.err
            assert working.read_bytes() != before
            written = working.read_text(encoding="utf-8")
            for line in supported:
                assert f"- {line}" in written
