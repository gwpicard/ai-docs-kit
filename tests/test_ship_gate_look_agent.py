"""Issue 384: engine coverage cannot stand in for a look agent's findings."""

import importlib
import json
import runpy
from pathlib import Path

import pytest

from ai_docs_kit import cli
from ai_docs_kit.store import load_version
from ai_docs_kit.store.gate import ship_gate

ORACLE = Path(__file__).parent / "judge" / "test_m1_17_cli_build_check.py"
SLIDES = runpy.run_path(str(ORACLE))["SLIDES"]
HEADER, FIRST, SECOND = SLIDES.split("\n::: ", 2)
MISSING_AGENT = "not looked at by the look agent"
ENGINE_PROBLEM = "semantic page 2: timeout"


@pytest.fixture(params=["statement-first", "bullets-first"])
def source(tmp_path, request):
    sections = (FIRST, SECOND) if request.param == "statement-first" else (SECOND, FIRST)
    path = tmp_path / "deck.md"
    path.write_text(HEADER + "".join("\n::: " + section for section in sections), encoding="utf-8")
    return path


def run(args, capsys):
    code = cli.main(args)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def build(source, capsys, *, final=False):
    args = ["build", str(source), "--out", str(source.parent / "out")]
    if final:
        args.append("--final")
    result = run(args, capsys)
    version = source.with_suffix(".versions") / "v1"
    assert (version / "manifest.json").is_file(), result
    return result, version


def record_empty(version, capsys):
    findings = version.parent.parent / "agent-findings.json"
    findings.write_text("[]\n", encoding="utf-8")
    return run(["look", str(version), "--findings", str(findings)], capsys)


def seed_engine_problem(monkeypatch):
    """Keep the real render and checks, but seed unavailable engine coverage."""
    engine = importlib.import_module("ai_docs_kit.loop.look")
    original = engine.look

    async def incomplete(pdf, comp, ctx):
        result = await original(pdf, comp, ctx)
        return result.model_copy(update={"could_not": [ENGINE_PROBLEM]})

    monkeypatch.setattr(engine, "look", incomplete)


def test_gate_refuses_unread_fixture_then_accepts_the_same_version_with_empty_findings(source, capsys):
    (code, out, err), version = build(source, capsys)
    assert code == 0 and err == "", (out, err)
    before = load_version(version)
    assert before.manifest.findings.error == 0 and before.manifest.gaps == []
    engine_record = before.manifest.look
    assert engine_record is not None
    assert engine_record.agent is None
    assert engine_record.pages == 2 and engine_record.method == "marks" and engine_record.clean
    assert engine_record.could_not == []
    assert engine_record.tiers == {"source": "ok", "geometry": "ok", "pixel": "ok", "semantic": "skipped"}
    unread_reasons = ship_gate(before)

    # Exercise the passing twin before asserting the missing refusal, so both run on the defective engine.
    code, out, err = record_empty(version, capsys)
    assert code == 0 and err == "", (out, err)
    after = load_version(version)
    assert after.manifest.look is not None and after.manifest.look.agent == []
    assert after.manifest.look.model_dump(exclude={"agent"}) == engine_record.model_dump(exclude={"agent"})
    assert ship_gate(after) == []
    saved = (version / "manifest.json").read_bytes()
    assert record_empty(version, capsys)[0] == 0
    assert (version / "manifest.json").read_bytes() == saved
    assert unread_reasons == [MISSING_AGENT], "an engine page pass alone must not pass the ship gate"


def test_final_build_refuses_a_clean_version_without_agent_findings(source, capsys):
    (code, out, err), version = build(source, capsys, final=True)
    manifest = json.loads((version / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["final"] is True and manifest["look"]["agent"] is None
    assert manifest["look"]["clean"] is True and manifest["findings"]["error"] == 0
    assert (code, out.splitlines(), err) == (
        1,
        [str(source.parent / "out" / "deck.pdf"), str(version), f"not ready: {MISSING_AGENT}"],
        "",
    )


def test_missing_agent_reason_follows_existing_engine_error_and_gap_reasons(source, capsys, monkeypatch):
    source.write_text(
        source.read_text(encoding="utf-8").replace("- Cheap to repeat.", "- [GAP: owner name]"),
        encoding="utf-8",
    )
    seed_engine_problem(monkeypatch)
    (code, out, err), version = build(source, capsys, final=True)
    assert code == 1 and err == "", (out, err)
    stored = load_version(version)
    assert stored.manifest.findings.error > 0 and len(stored.manifest.gaps) == 1
    assert ship_gate(stored) == [
        f"not fully looked at: {ENGINE_PROBLEM}",
        f"{stored.manifest.findings.error} error findings",
        "1 gaps",
        MISSING_AGENT,
    ]


@pytest.mark.parametrize("incomplete", [False, True], ids=["complete-engine", "incomplete-engine"])
def test_findings_summary_names_the_engine_page_pass(source, capsys, monkeypatch, incomplete):
    if incomplete:
        seed_engine_problem(monkeypatch)
    (code, out, err), version = build(source, capsys)
    assert code == 0 and err == "", (out, err)
    code, out, err = record_empty(version, capsys)
    assert code == 0 and err == "", (out, err)
    assert "recorded 0 findings" in out.splitlines()
    assert "open errors: 0" in out
    assert (ENGINE_PROBLEM if incomplete else "none") in out
    assert "engine page pass" in out and "looked at" not in out, out


def test_final_build_names_incomplete_engine_coverage_without_claiming_agent_coverage(source, capsys, monkeypatch):
    seed_engine_problem(monkeypatch)
    (code, out, err), version = build(source, capsys, final=True)
    assert code == 1 and err == "", (out, err)
    record = load_version(version).manifest.look
    assert record is not None and record.could_not == [ENGINE_PROBLEM] and record.agent is None
    engine_lines = [line for line in out.splitlines() if line.startswith("not ready: ") and ENGINE_PROBLEM in line]
    assert len(engine_lines) == 1, out
    assert "engine page pass" in engine_lines[0] and "looked at" not in engine_lines[0], out
    assert f"not ready: {MISSING_AGENT}" in out.splitlines()
