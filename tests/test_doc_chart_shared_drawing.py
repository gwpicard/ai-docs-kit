"""Document charts share signed geometry without changing slides or Word references."""

import json
import shutil
from pathlib import Path

import pytest
from docx import Document as WordDocument

from ai_docs_kit.cli import main
from ai_docs_kit.facts.layout import LayoutFacts, layout_facts
from ai_docs_kit.model import Document, Section
from ai_docs_kit.render.compose import font_paths
from ai_docs_kit.render.marks import ElementMark
from ai_docs_kit.source.serialiser import serialise
from ai_docs_kit.testing.golden import compare_facts, facts_for
from ai_docs_kit.theme import neutral_theme

FIXTURES = Path(__file__).resolve().parent / "fixtures/components"


def test_signed_doc_charts_keep_slide_golden_and_word_review_references(tmp_path, capsys):
    # The shared drawing must keep the established slide layout exactly as it was.
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    shutil.copyfile(FIXTURES / "chart.yaml", fixtures / "chart.yaml")
    expected = json.loads((FIXTURES / "chart.facts.json").read_bytes())
    assert compare_facts(facts_for("chart", fixtures), expected) == []

    sections = [
        Section(
            id=kind,
            intent="chart",
            title=f"Signed {kind} values",
            paragraphs=["Opening survey context.", "Closing survey limits."],
            content_order=["paragraphs[0]", "data", "paragraphs[1]"],
            data={
                "type": kind,
                "categories": ["Before", "None", "After"],
                "series": [
                    {"name": "Upland", "values": [-6, 0, 9]},
                    {"name": "Lowland", "values": [-3, 0, 6]},
                ],
            },
            source_line="Source: Synthetic survey register",
        )
        for kind in ("bar", "column")
    ]
    source = tmp_path / "signed.md"
    source.write_text(serialise(Document(front={}, format="doc", sections=sections)), encoding="utf-8")
    assert main(["build", str(source)]) == 0, capsys.readouterr()
    capsys.readouterr()
    version = tmp_path / "signed.versions/v1"
    composition = json.loads((version / "composition.json").read_bytes())
    assert [section["component"] for section in composition["sections"]] == ["doc-chart", "doc-chart"]
    facts = LayoutFacts.model_validate_json((version / "layout.json").read_bytes())
    for section in sections:
        marks = {
            mark.field: mark
            for mark in facts.marks
            if isinstance(mark, ElementMark) and mark.id == section.id and mark.role == "chart-mark"
        }
        assert len(marks) == 6
        for j in range(2):
            negative, zero, positive = [marks[f"data.series[{j}].values[{i}]"] for i in range(3)]
            if section.id == "bar":
                assert negative.x + negative.w == pytest.approx(zero.x, abs=0.02)
                assert positive.x == pytest.approx(zero.x, abs=0.02)
                assert zero.w == 0
                assert positive.w / negative.w == pytest.approx(1.5 if j == 0 else 2, abs=0.02)
            else:
                assert positive.y + positive.h == pytest.approx(zero.y, abs=0.02)
                assert negative.y == pytest.approx(zero.y, abs=0.02)
                assert zero.h == 0
                assert positive.h / negative.h == pytest.approx(1.5 if j == 0 else 2, abs=0.02)
    findings = json.loads((version / "findings.json").read_bytes())
    assert not [finding for finding in findings if finding["rule_id"] in {"data.values-visible", "geo.text-present"}]
    word = WordDocument(str(version / "signed.docx"))
    assert [paragraph.text for paragraph in word.paragraphs] == [
        line
        for i, section in enumerate(sections, 1)
        for line in [section.paragraphs[0], f"[Chart {i}: {section.title}]", section.paragraphs[1]]
    ]
    returned = tmp_path / "signed-reviewed.docx"
    shutil.copyfile(version / "signed.docx", returned)
    assert main(["review", "read", str(returned)]) == 0, capsys.readouterr()
    plan = json.loads((version / "review-plan.json").read_bytes())
    assert all(section["wording"] is None for section in plan["sections"].values())
    assert plan["confirm"] == []


def test_explicit_doc_chart_override_falls_back_for_unsupported_data(tmp_path, capsys):
    section = Section(
        id="fallback",
        intent="chart",
        title="Survey shares",
        component="doc-chart",
        because="Exercise the document component with an unsupported chart type.",
        data={
            "type": "pie",
            "categories": ["Upland", "Lowland"],
            "series": [{"name": "Visits", "values": [17, 29]}],
        },
    )
    source = tmp_path / "fallback.md"
    source.write_text(serialise(Document(front={}, format="doc", sections=[section])), encoding="utf-8")
    assert main(["build", str(source)]) == 0, capsys.readouterr()
    capsys.readouterr()
    version = tmp_path / "fallback.versions/v1"
    facts = LayoutFacts.model_validate_json((version / "layout.json").read_bytes())
    roles = [mark.role for mark in facts.marks if isinstance(mark, ElementMark)]
    assert "chart-mark" not in roles
    assert roles.count("table-cell") == 4
    findings = json.loads((version / "findings.json").read_bytes())
    assert not [finding for finding in findings if finding["rule_id"] == "data.values-visible"]


def test_brand_specimens_include_document_charts_and_keep_slide_specimens_working(tmp_path, capsys):
    root = tmp_path / "brands"
    assert main(["brand", "init", "sample", "--root", str(root)]) == 0, capsys.readouterr()
    brand = root / "sample"
    shutil.copytree(neutral_theme().root, brand / "theme", dirs_exist_ok=True)
    capsys.readouterr()
    for doctype in ("report", "pitch-deck"):
        args = ["brand", "specimen", "sample", "--root", str(root), "--doctype", doctype]
        assert main(args) == 0, capsys.readouterr()
        capsys.readouterr()
        records = list((brand / "theme/ingest/work/specimens" / doctype).glob("*/specimen.json"))
        assert len(records) == 1
        record = json.loads(records[0].read_bytes())
        components = {component for page in record["pages"] for component in page["components"]}
        if doctype == "report":
            assert {"doc-chart", "chart-table"} <= components
            render = records[0].parent / "render"
            facts = layout_facts(brand / record["pdf"], render / "main.typ", render, font_paths=font_paths(render))
            assert (
                sum(
                    isinstance(mark, ElementMark) and mark.id == "s-doc-chart" and mark.role == "chart-mark"
                    for mark in facts.marks
                )
                == 36
            )
        else:
            assert "chart" in components and "doc-chart" not in components
        pdf = brand / record["pdf"]
        before = pdf.stat().st_mtime_ns
        assert main(args) == 0, capsys.readouterr()
        capsys.readouterr()
        assert pdf.stat().st_mtime_ns == before
