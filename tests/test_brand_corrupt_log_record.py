"""A damaged brand change record is named and refused without a traceback."""

import subprocess
import sys
from pathlib import Path

import pytest


def _run(*args):
    return subprocess.run(
        [str(Path(sys.executable).with_name("ai-docs-kit")), *map(str, args)],
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.mark.parametrize("damaged", ["", "{", "{}"])
def test_brand_log_reports_a_damaged_change_record_cleanly(tmp_path, damaged):
    root = tmp_path / ".brand"
    initialised = _run("brand", "init", "synthetic", "--root", root)
    assert initialised.returncode == 0, initialised.stderr
    args = ("brand", "log", "synthetic", "--root", root)
    control = _run(*args)
    assert control.returncode == 0, control.stderr
    assert control.stdout.strip() == "no changes"
    record = root / "synthetic" / "changes" / "0001-example" / "record.json"
    record.parent.mkdir(parents=True)
    record.write_text(damaged, encoding="utf-8")

    result = _run(*args)

    assert result.returncode == 2, result.stderr
    assert "record.json" in result.stderr
    assert "Traceback" not in result.stderr
    assert len(result.stderr.strip().splitlines()) == 1
    assert record.read_text(encoding="utf-8") == damaged
