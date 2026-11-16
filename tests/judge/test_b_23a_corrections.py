# Intent: Confirm, reject and explain calibration corrections with reviewable brand changes.
import importlib
import importlib.util
import os
import shutil
import subprocess

import pytest
import yaml
from PIL import Image

from ai_docs_kit import cli
from ai_docs_kit.brand.git import run_git
from ai_docs_kit.brand.workspace import BrandError, init_brand
from ai_docs_kit.doctypes import Doctype
from ai_docs_kit.theme import load_theme, neutral_theme


def _optional(name):
    try:
        return importlib.import_module(name)
    except ImportError as error:
        missing = error.name or ""
        if not (missing == name or name.startswith(missing + ".") or missing.startswith(name + ".")):
            raise
        if importlib.util.find_spec(missing) is not None:
            raise
        return None


corrections = _optional("ai_docs_kit.brand.corrections")


def _require():
    assert corrections is not None, "ai_docs_kit.brand.corrections must exist"
    for name in (
        "find_correction",
        "specimen_page_png",
        "confirm_correction",
        "reject_correction",
        "explain_correction",
    ):
        assert hasattr(corrections, name), f"ai_docs_kit.brand.corrections.{name} must exist"


def _git(brand, *args):
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    return subprocess.run(["git", *args], cwd=brand, env=env, check=True, text=True, capture_output=True).stdout.strip()


def _setup(tmp_path):
    from ai_docs_kit.brand.calibrate import CalibrationRun, Correction, save_run
    from ai_docs_kit.theme.labels import ValueProvenance, ValueSource, token_paths

    brand = init_brand("acme", tmp_path / ".brand")
    shutil.rmtree(brand / "theme")
    shutil.copytree(neutral_theme().root, brand / "theme")
    info_path = brand / "theme/theme.yaml"
    info = yaml.safe_load(info_path.read_text())
    info["labelled"] = True
    info_path.write_text(yaml.safe_dump(info, sort_keys=False))
    answered = ValueProvenance(label="answered", source=ValueSource(question="q-1"))
    measured = ValueProvenance(
        label="measured",
        source=ValueSource(file="materials/guidelines/book.pdf", role="guidelines", page=2, quote="Margins are 40 pt"),
    )
    paths = token_paths(brand / "theme/tokens.yaml")
    labels = {path: answered.model_dump(exclude_none=True) for path in paths}
    labels["pages.slides.margin.left"] = measured.model_dump(exclude_none=True)
    (brand / "theme/provenance.yaml").write_text(yaml.safe_dump({"tokens": labels}, sort_keys=False))
    doctypes = []
    for name, fmt, intent in (("cover-only", "slides", "cover"), ("body-only", "doc", "body")):
        doctype = Doctype(
            name=name,
            format=fmt,
            audience="Readers",
            length={"slides" if fmt == "slides" else "pages": (1, 1)},
            questions=[],
            outline=[{"section": intent, "intent": intent, "required": True}],
            checks=[],
            checklist=[],
        )
        doctypes.append(doctype)
        folder = brand / "theme/doctypes"
        folder.mkdir(exist_ok=True)
        (folder / f"{name}.yaml").write_text(
            yaml.safe_dump(doctype.model_dump(mode="json", by_alias=True, exclude_none=True), sort_keys=False)
        )
    run_git(brand, "add", "-A")
    run_git(brand, "commit", "-m", "Set up theme")
    for doctype, ident, component, token, before, after, file, page in (
        (
            doctypes[0],
            "111111111111",
            "cover",
            "pages.slides.margin.left",
            "40pt",
            "64pt",
            "materials/guidelines/book.pdf",
            2,
        ),
        (
            doctypes[1],
            "222222222222",
            "body",
            "pages.doc.margin.left",
            "20mm",
            "25mm",
            "materials/examples/report.pdf",
            1,
        ),
    ):
        correction = Correction(
            id=ident,
            component=component,
            format=doctype.format,
            area="margins",
            says="The margin is too narrow",
            token=token,
            before=before,
            after=after,
            brand_file=file,
            brand_page=page,
            specimen_page=1,
            round=1,
        )
        run = CalibrationRun(
            doctype=doctype.name,
            format=doctype.format,
            base_sha256="0" * 64,
            candidate="scratch",
            rounds=[],
            stopped="no-differences",
            corrections=[correction],
            remaining=[],
        )
        save_run(brand, run)
    return brand, doctypes


def _path(brand, value):
    from pathlib import Path

    return brand / Path(value)


def test_D1_confirm_records_evidence_renders_and_state(tmp_path):
    _require()
    from ai_docs_kit.brand.calibrate import load_run
    from ai_docs_kit.brand.changes import ChangeRecord
    from ai_docs_kit.brand.specimen import render_specimen
    from ai_docs_kit.theme.labels import token_label

    brand, (deck, _) = _setup(tmp_path)
    page = corrections.specimen_page_png(brand, render_specimen(brand, deck), "cover")
    original = page.read_bytes()
    record = corrections.confirm_correction(brand, deck, "111111111111", person="owner", note="Matches page 2")
    assert isinstance(record, ChangeRecord)
    assert record.id.endswith("correct-cover-margins")
    assert record.what == "Correct the margins of cover"
    assert "The margin is too narrow" in record.why and "Matches page 2" in record.why
    assert {"theme/tokens.yaml", "theme/provenance.yaml", "theme/departures.yaml"} <= set(record.files)
    assert record.formats == ["slides"] and record.person == "owner"
    assert len(record.before) == len(record.after) == 1
    assert _path(brand, record.before[0]).read_bytes() == original
    assert _path(brand, record.after[0]).read_bytes() != original
    assert any(e.file == "materials/guidelines/book.pdf" and e.page == 2 for e in record.evidence)
    theme = load_theme(brand / "theme")
    assert theme.tokens.pages["slides"].margin.left == 64.0
    assert token_label(theme, "pages.slides.margin.left").label == "answered"
    assert _git(brand, "branch", "--show-current") == "main"
    assert _git(brand, "status", "--porcelain") == ""
    correction = corrections.find_correction(load_run(brand, deck.name), "111111111111")
    assert (correction.state, correction.change, correction.person, correction.note) == (
        "confirmed",
        record.id,
        "owner",
        "Matches page 2",
    )
    tokens = (brand / "theme/tokens.yaml").read_bytes()
    head = _git(brand, "rev-parse", "HEAD")
    with pytest.raises(BrandError, match="confirmed"):
        corrections.confirm_correction(brand, deck, "111111111111")
    assert (brand / "theme/tokens.yaml").read_bytes() == tokens
    assert _git(brand, "rev-parse", "HEAD") == head


def test_D2_departure_and_report_format(tmp_path):
    _require()
    from ai_docs_kit.brand.departures import load_departures

    from ai_docs_kit.theme.models import to_pt

    brand, (deck, report) = _setup(tmp_path)
    corrections.confirm_correction(brand, deck, "111111111111")
    departures = load_departures(brand)
    assert len(departures) == 1
    dep = departures[0]
    assert (dep.status, dep.path, dep.source_value, dep.value, dep.approved_by) == (
        "active",
        "pages.slides.margin.left",
        "40pt",
        "64pt",
        "owner",
    )
    assert "The margin is too narrow" in dep.reason
    record = corrections.confirm_correction(brand, report, "222222222222")
    assert len(load_departures(brand)) == 1
    assert record.formats == ["doc"]
    for page in (record.before[0], record.after[0]):
        with Image.open(_path(brand, page)) as image:
            assert abs(image.height / image.width - 841.89 / 595.28) < 0.01
    assert abs(load_theme(brand / "theme").tokens.pages["doc"].margin.left - to_pt("25mm")) < 0.01


def test_D3_refusals_leave_tokens_and_history_unchanged(tmp_path):
    _require()
    from ai_docs_kit.brand.calibrate import load_run, save_run
    from ai_docs_kit.brand.changes import Evidence, begin_change, record_change
    from ai_docs_kit.brand.departures import set_token
    from ai_docs_kit.theme.labels import ValueProvenance, ValueSource

    brand, (deck, report) = _setup(tmp_path)
    tokens = brand / "theme/tokens.yaml"

    def refused(doctype, ident, match=None):
        before, head = tokens.read_bytes(), _git(brand, "rev-parse", "HEAD")
        with pytest.raises(BrandError, match=match):
            corrections.confirm_correction(brand, doctype, ident)
        assert tokens.read_bytes() == before
        assert _git(brand, "rev-parse", "HEAD") == head

    refused(deck, "ffffffffffff", "ffffffffffff")
    no_run = report.model_copy(update={"name": "missing-run"})
    refused(no_run, "111111111111")
    corrections.reject_correction(brand, deck.name, "111111111111")
    refused(deck, "111111111111", "rejected")
    run = load_run(brand, deck.name)
    run.corrections[0].state = "proposed"
    save_run(brand, run)
    begin_change(brand, "other-margin")
    set_token(
        brand,
        "pages.slides.margin.left",
        "50pt",
        provenance=ValueProvenance(label="answered", source=ValueSource(question="q-2")),
        reason="Changed",
        person="owner",
        approved=True,
    )
    record_change(
        brand,
        what="Change margin",
        why="Changed",
        evidence=[Evidence(file="theme/tokens.yaml")],
        before=[],
        after=[],
        formats=["slides"],
        person="owner",
    )
    refused(deck, "111111111111", "(?i)changed.*since")


def test_D4_reject_and_explain_persist_without_brand_changes(tmp_path):
    _require()
    from ai_docs_kit.brand.calibrate import load_run

    brand, (deck, report) = _setup(tmp_path)
    head = _git(brand, "rev-parse", "HEAD")
    result = corrections.reject_correction(brand, deck.name, "111111111111", note="The book is wrong here")
    assert (result.state, result.person, result.note) == ("rejected", "owner", "The book is wrong here")
    assert load_run(brand, deck.name).corrections[0].state == "rejected"
    result = corrections.explain_correction(brand, report.name, "222222222222", note="Only on covers")
    assert (result.state, result.person, result.note) == ("proposed", "owner", "Only on covers")
    assert load_run(brand, report.name).corrections[0].note == "Only on covers"
    with pytest.raises(BrandError):
        corrections.explain_correction(brand, report.name, "222222222222", note="  ")
    assert _git(brand, "rev-parse", "HEAD") == head


def test_D5_cli_lists_and_applies_corrections(tmp_path, capsys):
    _require()
    brand, (deck, _) = _setup(tmp_path)
    args = ["brand", "corrections", "acme", "--root", str(brand.parent), "--doctype", deck.name]
    assert cli.main(args) == 0
    output = capsys.readouterr().out
    assert "111111111111" in output and "proposed" in output and "pages.slides.margin.left" in output
    assert cli.main([*args, "--explain", "111111111111"]) == 2
    assert cli.main([*args, "--confirm", "ffffffffffff"]) == 2
    assert cli.main([*args, "--confirm", "111111111111"]) == 0
    assert "correct-cover-margins" in capsys.readouterr().out
