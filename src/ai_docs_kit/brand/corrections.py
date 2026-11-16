"""Review and apply proposed calibration corrections."""

import shutil
from pathlib import Path

from ai_docs_kit.brand.calibrate import (
    CalibrationRun,
    Correction,
    _leaf,
    _tokens,
    load_run,
    run_folder,
    save_run,
    set_token_value,
)
from ai_docs_kit.brand.changes import ChangeRecord, Evidence, begin_change, record_change
from ai_docs_kit.brand.departures import _proposal, set_token
from ai_docs_kit.brand.specimen import SpecimenRender, component_pages, render_specimen
from ai_docs_kit.brand.workspace import BrandError
from ai_docs_kit.doctypes import Doctype
from ai_docs_kit.theme import ThemeError, load_theme
from ai_docs_kit.theme.labels import ValueProvenance, ValueSource


def find_correction(run: CalibrationRun, correction_id: str) -> Correction:
    for correction in run.corrections:
        if correction.id == correction_id:
            return correction
    raise BrandError(f"Unknown correction: {correction_id}")


def _proposed(brand: Path, doctype_name: str, correction_id: str) -> tuple[CalibrationRun, Correction]:
    run = load_run(brand, doctype_name)
    if run is None:
        raise BrandError(f"No calibration run for {doctype_name}")
    correction = find_correction(run, correction_id)
    if correction.state != "proposed":
        raise BrandError(f"Correction {correction_id} is {correction.state}")
    return run, correction


def specimen_page_png(brand: Path, render: SpecimenRender, component: str) -> Path:
    page = component_pages(render).get(component)
    for item in render.pages:
        if item.page == page:
            return (brand / item.png).resolve()
    raise BrandError(f"No specimen page for {component}")


def confirm_correction(
    brand: Path, doctype: Doctype, correction_id: str, *, person: str = "owner", note: str | None = None
) -> ChangeRecord:
    run, correction = _proposed(brand, doctype.name, correction_id)
    try:
        current = _leaf(_tokens(brand / "theme"), correction.token)
    except KeyError as error:
        raise BrandError("Brand changed since the run; calibrate again") from error
    if current != correction.before:
        raise BrandError("Brand changed since the run; calibrate again")
    reason = correction.says + (f" Note: {note}" if note else "")
    try:
        _proposal(brand, correction.token, correction.after, reason)
        before = render_specimen(brand, doctype)
        candidate = run_folder(brand, doctype.name) / "confirm"
        if candidate.exists():
            shutil.rmtree(candidate)
        shutil.copytree(
            brand / "theme",
            candidate,
            ignore=lambda folder, names: (
                ["work"] if Path(folder) == brand / "theme" / "ingest" and "work" in names else []
            ),
        )
        set_token_value(candidate / "tokens.yaml", correction.token, correction.after)
        load_theme(candidate)
        after = render_specimen(brand, doctype, theme_root=candidate)
    except ThemeError as error:
        raise BrandError(str(error)) from error
    before_page = specimen_page_png(brand, before, correction.component)
    after_page = specimen_page_png(brand, after, correction.component)
    begin_change(brand, f"correct-{correction.component}-{correction.area}"[:41].rstrip("-"))
    departure = set_token(
        brand,
        correction.token,
        correction.after,
        provenance=ValueProvenance(
            label="answered",
            source=ValueSource(
                question=f"correction.{correction.id}",
                file=correction.brand_file,
                page=correction.brand_page,
                note=correction.says,
            ),
        ),
        reason=reason,
        person=person,
        approved=True,
    )
    evidence = [Evidence(file=correction.brand_file, page=correction.brand_page, note=correction.says)]
    if departure:
        source = departure.source.source
        files = ([source.file] if source.file else []) + source.files
        evidence.extend(Evidence(file=file, page=source.page, quote=source.quote) for file in files)
    record = record_change(
        brand,
        what=f"Correct the {correction.area} of {correction.component}",
        why=reason,
        evidence=evidence,
        before=[before_page],
        after=[after_page],
        formats=[correction.format],
        person=person,
    )
    correction.state = "confirmed"
    correction.change = record.id
    correction.person = person
    correction.note = note
    save_run(brand, run)
    return record


def reject_correction(
    brand: Path, doctype_name: str, correction_id: str, *, person: str = "owner", note: str | None = None
) -> Correction:
    run, correction = _proposed(brand, doctype_name, correction_id)
    correction.state = "rejected"
    correction.person = person
    correction.note = note
    save_run(brand, run)
    return correction


def explain_correction(
    brand: Path, doctype_name: str, correction_id: str, *, note: str, person: str = "owner"
) -> Correction:
    if not note.strip():
        raise BrandError("An explanation requires a note")
    run, correction = _proposed(brand, doctype_name, correction_id)
    correction.person = person
    correction.note = note
    save_run(brand, run)
    return correction
