"""One unreadable material file must not stop intake of the rest."""

import os
import zipfile
from pathlib import Path

import pytest

from ai_docs_kit.brand.intake import take_in


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read any file")
def test_unreadable_file_is_marked_unread_not_a_crash(tmp_path: Path) -> None:
    brand = tmp_path / "acme"
    folder = brand / "materials" / "templates"
    folder.mkdir(parents=True)
    with zipfile.ZipFile(folder / "good.docx", "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
    locked = folder / "locked.docx"
    locked.write_bytes(b"x")
    locked.chmod(0)
    try:
        manifest = take_in(brand)
    finally:
        locked.chmod(0o644)
    by_name = {Path(f.path).name: f for f in manifest.files}
    assert by_name["locked.docx"].unread is not None
    assert by_name["good.docx"].unread is None
