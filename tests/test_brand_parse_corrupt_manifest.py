"""Damaged intake records receive a clean refusal before brand parsing starts."""

import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("damaged", ["", "{", '{"brand": "synthetic", "files": [null]}'])
def test_brand_parse_refuses_a_damaged_intake_manifest_cleanly(tmp_path, damaged):
    root = tmp_path / ".brand"
    brand = root / "synthetic"
    brand.mkdir(parents=True)
    initialised = subprocess.run(["git", "init", "-b", "main", str(brand)], capture_output=True, text=True, timeout=30)
    assert initialised.returncode == 0, initialised.stderr
    ingest = brand / "theme" / "ingest"
    ingest.mkdir(parents=True)
    manifest = ingest / "manifest.json"
    manifest.write_text(json.dumps({"brand": "synthetic", "files": []}), encoding="utf-8")
    command = [str(Path(sys.executable).with_name("ai-docs-kit")), "brand", "parse", "synthetic", "--root", str(root)]
    control = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert control.returncode == 2
    assert "no readable PDFs" in control.stdout
    before = subprocess.run(
        ["git", "-C", str(brand), "status", "--porcelain"], capture_output=True, text=True, timeout=30
    )
    assert before.returncode == 0, before.stderr
    manifest.write_text(damaged, encoding="utf-8")

    result = subprocess.run(command, capture_output=True, text=True, timeout=60)

    assert result.returncode == 2, result.stderr
    assert "manifest.json" in result.stderr
    assert "Traceback" not in result.stderr
    assert len(result.stderr.strip().splitlines()) == 1
    assert manifest.read_text(encoding="utf-8") == damaged
