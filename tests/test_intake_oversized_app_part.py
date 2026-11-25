"""Intake must not inflate a hostile Office part without limit."""

import tracemalloc
import zipfile
from pathlib import Path

from ai_docs_kit.brand.intake import take_in


def _brand(tmp_path: Path, app: bytes) -> Path:
    brand = tmp_path / "acme"
    folder = brand / "materials" / "templates"
    folder.mkdir(parents=True)
    with zipfile.ZipFile(folder / "bomb.docx", "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("docProps/app.xml", app)
    return brand


def test_huge_app_part_is_marked_unread_without_inflating_it(tmp_path: Path) -> None:
    padding = b" " * (200 << 20)
    brand = _brand(tmp_path, b"<Properties><Pages>3</Pages></Properties>" + padding)
    tracemalloc.start()
    try:
        manifest = take_in(brand)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    entry = manifest.files[0]
    assert entry.unread is not None
    assert peak < 64 << 20
