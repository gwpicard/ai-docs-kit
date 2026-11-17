"""The test suite leaves tests/fixtures exactly as it found it (issue 33)."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
# A locked test that builds the pix.blank-page fixtures in place.
BUILDS_IN_PLACE = "tests/judge/test_m4_01_pixel_tier.py"


def snapshot() -> dict[str, tuple[str, int]]:
    """Every path under tests/fixtures, with its kind and file size."""
    seen = {}
    for path in sorted(FIXTURES.rglob("*")):
        kind = "dir" if path.is_dir() else "file"
        seen[str(path.relative_to(FIXTURES))] = (kind, 0 if path.is_dir() else path.stat().st_size)
    return seen


def run_pytest() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", BUILDS_IN_PLACE, "-q", "-p", "no:cacheprovider"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_in_place_builds_leave_no_new_paths_under_fixtures():
    before = snapshot()
    result = run_pytest()
    after = snapshot()
    assert result.returncode == 0, result.stdout + result.stderr
    created = sorted(set(after) - set(before))
    assert created == []
    assert after == before


def test_version_folder_from_before_the_run_survives_unchanged():
    seeded = FIXTURES / "seeded-defects" / "pix.blank-page" / "fail" / "doc.versions" / "v9"
    assert not seeded.exists()
    seeded.mkdir(parents=True)
    marker = seeded / "marker.txt"
    marker.write_text("keep me")
    try:
        result = run_pytest()
        assert result.returncode == 0, result.stdout + result.stderr
        assert marker.read_text() == "keep me"
    finally:
        marker.unlink(missing_ok=True)
        seeded.rmdir()
