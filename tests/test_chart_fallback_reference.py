"""The authoring reference describes each format's actual chart fallback."""

import re
from pathlib import Path

import pytest
import yaml

from ai_docs_kit.cli import main
from ai_docs_kit.facts.layout import LayoutFacts
from ai_docs_kit.render.marks import ElementMark

REFERENCE = Path(__file__).resolve().parents[1] / "skills/create/working-file.md"


@pytest.mark.parametrize("fmt, requested", [("doc", "pie"), ("slides", "line")])
def test_reference_fallback_matches_cli_build_with_drawable_control(tmp_path, capsys, fmt, requested):
    for kind in ("column", requested):
        folder = tmp_path / kind
        folder.mkdir()
        source = folder / "chart.md"
        data = {
            "type": kind,
            "category_label": "Zone",
            "categories": ["Upland", "Lowland"],
            "series": [{"name": "Trips", "values": [12, 18]}],
            "unit": "kg",
        }
        source.write_text(
            f'---\nformat: {fmt}\n---\n\n::: {{#chartref .section intent="chart"}}\n'
            "## Survey results\n\n```data\n" + yaml.safe_dump(data, sort_keys=False) + "```\n:::\n",
            encoding="utf-8",
        )
        code = main(["build", str(source)])
        captured = capsys.readouterr()
        assert code == 0, captured.out + captured.err
        facts = LayoutFacts.model_validate_json((folder / "chart.versions/v1/layout.json").read_bytes())
        roles = {mark.role for mark in facts.marks if isinstance(mark, ElementMark) and mark.id == "chartref"}
        text = "".join("".join(word.text for word in facts.words).split())
        notice = "charttypenotsupported"
        if kind == "column":
            assert "chart-mark" in roles and "table-cell" not in roles
            assert notice not in text
        elif fmt == "doc":
            assert "table-cell" in roles and "chart-mark" not in roles
            assert all(value in text for value in ("Upland", "Lowland", "Trips", "12kg", "18kg"))
            assert notice not in text
        else:
            assert not roles.intersection({"chart-mark", "chart-label", "chart-legend", "table-cell"})
            assert notice in text
            assert all(value not in text for value in ("Upland", "Lowland", "Trips", "12kg", "18kg"))

    prose = " ".join(REFERENCE.read_text(encoding="utf-8").split())
    if fmt == "doc":
        assert re.search(r"In documents,[^.]*unsupported type[^.]*table fallback[^.]*without[^.]*notice", prose)
    else:
        assert re.search(
            r"For slides,[^.]*`bar` and `column`[^.]*\. Other requested types,[^.]*`line`[^.]*`pie`"
            r"[^.]*`chart type not supported`[^.]*without a table or data values",
            prose,
        )
