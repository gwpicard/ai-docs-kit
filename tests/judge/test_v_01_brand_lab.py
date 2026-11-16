# Intent: Run brand setup on owner materials and report where it stops.
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/brand_lab.py"
STEPS = (
    "intake",
    "fonts",
    "gaps",
    "parse",
    "templates",
    "segment",
    "extract",
    "measure",
    "tie",
    "reconcile",
    "synthesise",
    "specimen",
)
FONTS = ("Inter-Regular.ttf", "Inter-SemiBold.ttf", "SourceSerif4-Regular.ttf")


@pytest.fixture
def subject():
    if not SCRIPT.is_file():
        yield None
        return
    spec = importlib.util.spec_from_file_location("brand_lab", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        try:
            spec.loader.exec_module(module)
        except ImportError as error:
            name = error.name or ""
            if name == "brand_lab" or name.startswith("brand_lab."):
                raise AssertionError(f"brand lab public interface is missing: {name}") from None
            raise
        assert callable(getattr(module, "main", None)), "brand_lab.main must exist"
        yield module
    finally:
        sys.modules.pop(spec.name, None)


def make_lab(tmp_path):
    from ai_docs_kit.render.typst import compile_pdf

    lab = tmp_path / "lab/acme"
    for folder in ("guidelines", "examples", "fonts", "misc"):
        (lab / folder).mkdir(parents=True)
    fonts = ROOT / "src/ai_docs_kit/themes/neutral/fonts"
    for name in FONTS:
        shutil.copy2(fonts / name, lab / "fonts" / name)
    (lab / "fonts/fonts.yaml").write_text(
        "typefaces: [Inter, Source Serif 4]\nfonts:\n"
        "  - {file: Inter-Regular.ttf, family: Inter, weight: 400, licence: OFL-1.1}\n"
        "  - {file: Inter-SemiBold.ttf, family: Inter, weight: 600, licence: OFL-1.1}\n"
        "  - {file: SourceSerif4-Regular.ttf, family: Source Serif 4, weight: 400, licence: OFL-1.1}\n"
    )
    source = tmp_path / "source.typ"
    source.write_text(
        "#set page(width: 960pt, height: 540pt)\nAcme brand guidelines\\\n"
        "Version 3.2\\\nMarch 2025\n#pagebreak()\nColour guidelines"
    )
    compile_pdf(source, tmp_path, lab / "guidelines/book.pdf", [fonts])
    source.write_text('#set page(paper: "a4")\nAcme report')
    compile_pdf(source, tmp_path, lab / "examples/report.pdf", [fonts])
    (lab / ".DS_Store").write_text("ignored")
    (lab / "misc/readme.txt").write_text("ignored")
    return lab


def snapshot(lab):
    return {
        p.relative_to(lab).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns) for p in lab.rglob("*") if p.is_file()
    }


def git(brand, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(["git", *args], cwd=brand, env=env, check=True, capture_output=True, text=True).stdout


def report(brand):
    return (brand / "theme/ingest/work/lab/report.md").read_text()


def args(tmp_path, *extra):
    return ["acme", "--lab", str(tmp_path / "lab"), "--root", str(tmp_path / ".brand"), *extra]


def fake_model(monkeypatch):
    from ai_docs_kit.agents.client import Claude
    from ai_docs_kit.brand import agents
    from ai_docs_kit.testing.fakes import FakeTransport, fake_response

    class Ledger:
        def add(self, *args, **kwargs):
            pass

    def make_claude(brand):
        reply = {"pages": [{"page": 1, "topics": ["colour"]}, {"page": 2, "topics": ["other"]}]}
        return Claude(
            FakeTransport({"seg": [fake_response(json.dumps(reply))]}),
            Ledger(),
            {"brand.segment": "seg", "brand.extract": "ext"},
        )

    monkeypatch.setattr(agents, "brand_claude", make_claude)


def first_run(module, tmp_path):
    lab = make_lab(tmp_path)
    assert module.main(args(tmp_path)) == 1
    return lab, tmp_path / ".brand/acme"


def test_D1_initial_setup_stops_for_owner(subject, tmp_path):
    assert subject is not None, "scripts/brand_lab.py must exist"
    from ai_docs_kit.brand.changes import change_log

    lab, brand = first_run(subject, tmp_path)
    for relative in ["guidelines/book.pdf", "examples/report.pdf", *(f"fonts/{n}" for n in FONTS)]:
        assert (brand / "materials" / relative).read_bytes() == (lab / relative).read_bytes()
    assert not list(brand.rglob(".DS_Store"))
    assert not list(brand.rglob("readme.txt"))
    text = report(brand)
    for step, status in [
        ("intake", "ok"),
        ("fonts", "ok"),
        ("gaps", "questions"),
        *((s, "not run") for s in STEPS[3:]),
    ]:
        assert f"- {step}: {status}" in text
    assert "identity.earlier [blocking]" in text
    assert "Ignored: misc" in text
    assert "3 brand changes" in text
    assert [item.what for item in change_log(brand)] == [
        "Take in materials",
        "Check the brand's fonts",
        "Record what the brand does not provide",
    ]
    assert git(brand, "branch", "--show-current").strip() == "main"
    assert git(brand, "status", "--porcelain") == ""


def test_D2_resume_failure_cleans_branch(subject, tmp_path, monkeypatch):
    assert subject is not None, "scripts/brand_lab.py must exist"
    from ai_docs_kit.brand.changes import change_log

    lab, brand = first_run(subject, tmp_path)
    shutil.copy2(lab / "examples/report.pdf", lab / "examples/extra.pdf")
    fake_model(monkeypatch)
    assert subject.main(args(tmp_path, "--from", "parse", "--past-questions")) == 2
    text = report(brand)
    assert "1 copied, 6 unchanged" in text
    for step, status in [
        ("parse", "ok"),
        ("templates", "skipped"),
        ("segment", "ok"),
        ("extract", "failed"),
        *((s, "not run") for s in STEPS[7:]),
    ]:
        assert f"- {step}: {status}" in text
    assert "no PowerPoint or Word files" in text
    assert "No response for model ext" in text.split("## Output of extract", 1)[1].split("## ", 1)[0]
    assert git(brand, "log", "--format=%s").splitlines().count("Start brand acme") == 1
    assert git(brand, "branch", "--show-current").strip() == "main"
    assert git(brand, "status", "--porcelain") == ""
    assert not any("change/" in line and "extract" in line for line in git(brand, "branch").splitlines())
    assert change_log(brand)[-1].what == "Sort the guidelines' pages into topics"


def test_D3_order_failures_and_questions(subject, tmp_path, monkeypatch):
    assert subject is not None, "scripts/brand_lab.py must exist"
    from ai_docs_kit.brand.questions import BrandQuestion, add_questions

    from ai_docs_kit.brand.workspace import init_brand

    lab = tmp_path / "lab/acme"
    (lab / "fonts").mkdir(parents=True)
    (lab / "fonts/font.ttf").write_bytes(b"font")
    brand = init_brand("acme", tmp_path / ".brand")
    calls = []

    def recorder(argv):
        calls.append(argv)
        return (2, "boom") if argv[1] == "reconcile" else (0, "")

    monkeypatch.setattr(subject, "run_command", recorder)
    assert subject.main(args(tmp_path, "--from", "measure")) == 2
    assert calls == [
        ["brand", step, "acme", "--root", str(tmp_path / ".brand")] for step in ("measure", "tie", "reconcile")
    ]
    assert "- synthesise: not run" in report(brand)
    assert "- specimen: not run" in report(brand)
    calls.clear()
    monkeypatch.setattr(subject, "run_command", lambda argv: calls.append(argv) or (0, ""))
    assert subject.main(args(tmp_path)) == 0
    assert [call[1] for call in calls] == [s for s in STEPS if s != "templates"]

    for blocking, past, expected in [(True, False, 1), (True, True, 0), (False, False, 0)]:
        calls.clear()
        question_id = f"font.test-{blocking}-{past}"

        def question_recorder(argv, question_id=question_id, blocking=blocking):
            calls.append(argv[1])
            if argv[1] == "tie":
                add_questions(
                    brand, [BrandQuestion(id=question_id, kind="font", text="Supply font?", blocking=blocking)]
                )
            return 0, ""

        monkeypatch.setattr(subject, "run_command", question_recorder)
        extra = ("--past-questions",) if past else ()
        assert subject.main(args(tmp_path, "--from", "tie", *extra)) == expected
        assert calls == (["tie"] if expected == 1 else ["tie", "reconcile", "synthesise", "specimen"])
        if expected == 1:
            assert "- tie: questions" in report(brand)
            assert question_id in report(brand)


def test_D4_refusals_and_default_lab(subject, tmp_path, monkeypatch, capsys):
    assert subject is not None, "scripts/brand_lab.py must exist"
    root = tmp_path / ".brand"
    assert subject.main(args(tmp_path)) == 2
    assert "no lab folder:" in capsys.readouterr().err
    assert not root.exists()
    try:
        code = subject.main(args(tmp_path, "--from", "nosuch"))
    except SystemExit as exit:
        code = exit.code
    assert code == 2, f"an unknown --from step must exit with 2, got {code!r}"
    assert not root.exists()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert subject.default_lab() == tmp_path / "home/Documents/ai_docs_kit-brand-lab"


def test_D5_lab_materials_are_never_modified(subject, tmp_path, monkeypatch):
    assert subject is not None, "scripts/brand_lab.py must exist"
    lab = make_lab(tmp_path)
    before = snapshot(lab)
    assert subject.main(args(tmp_path)) == 1
    assert snapshot(lab) == before
    shutil.copy2(lab / "examples/report.pdf", lab / "examples/extra.pdf")
    before = snapshot(lab)
    fake_model(monkeypatch)
    assert subject.main(args(tmp_path, "--from", "parse", "--past-questions")) == 2
    assert snapshot(lab) == before
