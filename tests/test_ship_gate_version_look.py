"""Issue 384: a recorded agent look belongs to one built version only."""

import json
import runpy
from pathlib import Path

import pytest

from ai_docs_kit import cli
from ai_docs_kit.store import load_version
from ai_docs_kit.store.gate import ship_gate

ORACLE = Path(__file__).parent / "judge" / "test_m1_17_cli_build_check.py"
HEADER, FIRST, SECOND = runpy.run_path(str(ORACLE))["SLIDES"].split("\n::: ", 2)
MISSING_AGENT = "not looked at by the look agent"


@pytest.fixture(params=[False, True], ids=["statement-first", "bullets-first"])
def source(tmp_path, request):
    sections = (SECOND, FIRST) if request.param else (FIRST, SECOND)
    path = tmp_path / "deck.md"
    path.write_text(HEADER + "".join("\n::: " + section for section in sections), encoding="utf-8")
    return path


def run(args, capsys):
    code = cli.main(args)
    output = capsys.readouterr()
    return code, output.out, output.err


def record_empty(version, capsys):
    findings = version.parent / "empty-findings.json"
    findings.write_text("[]\n", encoding="utf-8")
    code, out, err = run(["look", str(version), "--findings", str(findings)], capsys)
    assert code == 0 and err == "", (out, err)
    return out


def test_a_new_final_version_needs_its_own_agent_findings(source, capsys):
    outdir = source.parent / "out"
    code, out, err = run(["build", str(source), "--out", str(outdir)], capsys)
    assert code == 0 and err == "", (out, err)
    first = source.with_suffix(".versions") / "v1"
    unread = load_version(first)
    assert unread.manifest.look is not None and unread.manifest.look.agent is None
    assert unread.manifest.findings.error == 0 and unread.manifest.gaps == []
    first_reasons = ship_gate(unread)

    record_empty(first, capsys)
    assert load_version(first).manifest.look.agent == []
    assert ship_gate(load_version(first)) == []
    first_manifest = (first / "manifest.json").read_bytes()

    final_result = run(["build", "--final", str(source), "--out", str(outdir)], capsys)
    second = first.parent / "v2"
    built = load_version(second)
    assert built.manifest.final and built.manifest.findings.error == 0 and built.manifest.gaps == []
    engine = built.manifest.look
    assert engine is not None and engine.agent is None
    assert engine.clean and engine.pages == 2 and engine.method == "marks" and engine.could_not == []
    assert engine.tiers == {"source": "ok", "geometry": "ok", "pixel": "ok", "semantic": "skipped"}
    second_reasons = ship_gate(built)

    # Run the passing twin too, before checking either missing-agent refusal.
    record_empty(second, capsys)
    looked = load_version(second).manifest.look
    assert looked is not None and looked.agent == []
    assert looked.model_dump(exclude={"agent"}) == engine.model_dump(exclude={"agent"})
    assert ship_gate(load_version(second)) == []
    assert (first / "manifest.json").read_bytes() == first_manifest
    assert ship_gate(load_version(first)) == []
    assert first_reasons == second_reasons == [MISSING_AGENT]
    assert final_result == (
        1,
        f"{outdir / 'deck.pdf'}\n{second}\nnot ready: {MISSING_AGENT}\n",
        "",
    )


def test_agent_error_summary_keeps_the_engine_page_pass_separate(source, capsys):
    code, out, err = run(["build", str(source), "--out", str(source.parent / "out")], capsys)
    assert code == 0 and err == "", (out, err)
    version = source.with_suffix(".versions") / "v1"
    before = load_version(version).manifest.look
    assert before is not None and before.clean and before.agent is None
    assert load_version(version).manifest.findings.error == 0
    pages = json.loads((version / "pages" / "pages.json").read_text(encoding="utf-8"))["pages"]
    findings = version.parent / "agent-error.json"
    findings.write_text(
        json.dumps(
            [
                {
                    "severity": "error",
                    "rule": "look.cut-off",
                    "page": pages[0]["page"],
                    "section": pages[0]["sections"][0],
                    "message": "The heading is cut off.",
                }
            ]
        ),
        encoding="utf-8",
    )
    code, out, err = run(["look", str(version), "--findings", str(findings)], capsys)
    assert code == 0 and err == "", (out, err)
    after = load_version(version).manifest.look
    assert after is not None and after.agent is not None and len(after.agent) == 1
    assert after.agent[0].severity == "error"
    assert after.model_dump(exclude={"agent"}) == before.model_dump(exclude={"agent"})
    assert out.splitlines() == [
        "recorded 1 findings",
        "open errors: 1, engine page pass could not check: none",
    ]
