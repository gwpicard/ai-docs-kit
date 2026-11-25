"""Pair the locked readable controls with hostile archives in every case."""

from pathlib import Path

import pytest

from test_intake_archive_limits import test_office_archive_limits as assert_archive_limits


@pytest.mark.parametrize("suffix", ["docx", "dotx", "pptx", "potx"])
@pytest.mark.parametrize("defect", ["part-size", "compression-ratio", "entry-count"])
def test_readable_and_hostile_office_archives(tmp_path: Path, suffix: str, defect: str) -> None:
    assert_archive_limits(tmp_path / "readable", suffix, None)
    assert_archive_limits(tmp_path / "hostile", suffix, defect)
