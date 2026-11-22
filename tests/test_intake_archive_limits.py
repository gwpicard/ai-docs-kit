"""Exercise Office intake limits through the persisted manifest."""

import zipfile
from pathlib import Path

import pytest

from ai_docs_kit.brand.intake import MANIFEST, Manifest, take_in


@pytest.mark.parametrize("suffix", ["docx", "dotx", "pptx", "potx"])
@pytest.mark.parametrize("defect", ["part-size", "compression-ratio", "entry-count"])
def test_office_archive_limits(tmp_path: Path, suffix: str, defect: str | None) -> None:
    brand = tmp_path / "acme"
    templates = brand / "materials" / "templates"
    templates.mkdir(parents=True)
    app = b"<Properties><Pages>3</Pages></Properties>"
    compression = zipfile.ZIP_STORED
    if defect == "part-size":
        app += b" " * ((32 << 20) + 1 - len(app))
    elif defect == "compression-ratio":
        app += b" " * (1 << 20)
        compression = zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(templates / f"sample.{suffix}", "w", compression) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("docProps/app.xml", app)
        archive.writestr("ppt/slides/slide1.xml", "<slide/>")
        if defect == "entry-count":
            for index in range(1998):
                archive.writestr(f"extra/{index}.xml", "<part/>")

    manifest = take_in(brand)

    assert Manifest.model_validate_json((brand / MANIFEST).read_text()) == manifest
    entry = manifest.files[0]
    assert entry.format == ("slides" if suffix in ("pptx", "potx") else "doc")
    if defect is None:
        assert entry.unread is None
        assert entry.pages == (1 if entry.format == "slides" else 3)
    else:
        assert entry.unread == f"sample.{suffix} is not a readable Office file"
        assert entry.pages is None


def test_total_archive_size_is_checked_before_reading_metadata(tmp_path: Path) -> None:
    brand = tmp_path / "acme"
    templates = brand / "materials" / "templates"
    templates.mkdir(parents=True)
    with zipfile.ZipFile(templates / "sample.docx", "w") as archive:
        archive.writestr("docProps/app.xml", "<Properties><Pages>3</Pages></Properties>")
        chunk = b" " * (1 << 20)
        for index in range(5):
            with archive.open(f"media/{index}.bin", "w") as stream:
                for _ in range(26):
                    stream.write(chunk)

    entry = take_in(brand).files[0]

    assert entry.unread == "sample.docx is not a readable Office file"
    assert entry.pages is None
