"""Line-end hyphens must preserve compound words without hiding real losses."""

import json
from pathlib import Path

import pytest

from ai_docs_kit import building, cli


@pytest.mark.parametrize("complete", [True, False], ids=["wrapped-compound", "lost-word"])
def test_mixed_inserted_and_original_hyphens_through_build(tmp_path, monkeypatch, capsys, complete):
    source = tmp_path / "report.md"
    source.write_text(
        '---\ndoctype: report\nformat: doc\n---\n\n::: {#access .section intent="body"}\n'
        "## Access findings\n\nNeighbourhood services keep a well-known route.\n:::\n",
        encoding="utf-8",
    )
    assemble = building.assemble

    def wrapped(comp, dest, **kwargs):
        assemble(comp, dest, **kwargs)
        main = dest / "wrapped-fixture.typ"
        main.write_text(
            '#import "/lib/theme.typ": colour, page-setup\n'
            '#import "/lib/marks.typ": section, el-full-width\n'
            '#show: page-setup.with("doc")\n#set text(fill: colour("ink"))\n'
            '#section("access", {\n'
            '  el-full-width("heading", "access", field: "title", [Access findings])\n'
            '  el-full-width("paragraph", "access", field: "paragraphs[0]", par([\n'
            "    Neigh-#linebreak()bourhood services keep a well-#linebreak()known "
            + ("route." if complete else ".")
            + "\n  ]))\n})\n",
            encoding="utf-8",
        )
        return main

    monkeypatch.setattr(building, "assemble", wrapped)
    assert cli.main(["build", str(source)]) == 0
    output = capsys.readouterr()
    assert output.err == ""
    version = Path(output.out.splitlines()[-1])
    findings = json.loads((version / "findings.json").read_text(encoding="utf-8"))
    hits = [finding for finding in findings if finding["rule_id"] == "geo.text-present"]
    assert len(hits) == (0 if complete else 1), hits
    if not complete:
        assert "paragraphs[0] missing from PDF" in hits[0]["message"]
    assert cli.main(["check", str(source)]) == (0 if complete else 1)
    assert capsys.readouterr().err == ""
