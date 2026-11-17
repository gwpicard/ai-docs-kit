import zipfile
from pathlib import Path

import pytest

from ai_docs_kit.brand.intake import take_in
from ai_docs_kit.brand.templates import read_templates


@pytest.mark.parametrize("name", ["deck.pptx", "report.docx"])
def test_plain_zip_named_as_office_file_is_unread(tmp_path: Path, name: str) -> None:
    brand = tmp_path / "acme"
    (brand / "materials" / "templates").mkdir(parents=True)
    with zipfile.ZipFile(brand / "materials" / "templates" / name, "w") as archive:
        archive.writestr("notes.txt", "not an office file")
    manifest = take_in(brand)
    assert manifest.files[0].unread is not None


@pytest.mark.parametrize("name", ["deck.pptx", "report.docx"])
def test_unread_reason_is_not_a_raw_exception(tmp_path: Path, name: str) -> None:
    brand = tmp_path / "acme"
    (brand / "materials" / "templates").mkdir(parents=True)
    with zipfile.ZipFile(brand / "materials" / "templates" / name, "w") as archive:
        archive.writestr("notes.txt", "not an office file")
    take_in(brand)
    manifest_path = brand / "theme" / "ingest"
    report = read_templates(brand)
    reasons = [u.reason for u in report.unread] if report.unread else []
    assert manifest_path is not None
    assert not any("KeyError" in r or "no member" in r or "no item named" in r for r in reasons)
    assert reasons or not report.templates
