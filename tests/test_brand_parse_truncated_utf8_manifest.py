"""A manifest truncated inside a UTF-8 character is refused without changes."""

import subprocess
import sys
from pathlib import Path

from ai_docs_kit.brand.intake import take_in


def test_brand_parse_refuses_a_manifest_truncated_inside_a_utf8_character(tmp_path):
    root = tmp_path / ".brand"
    brand = root / "synthetic"
    notes = brand / "materials" / "notes"
    notes.mkdir(parents=True)
    (notes / "café.txt").write_text("Synthetic notes.\n", encoding="utf-8")
    initialised = subprocess.run(["git", "init", "-b", "main", str(brand)], capture_output=True, text=True, timeout=30)
    assert initialised.returncode == 0, initialised.stderr
    take_in(brand)
    manifest = brand / "theme" / "ingest" / "manifest.json"
    intact = manifest.read_bytes()
    character = "é".encode()
    assert character in intact
    command = [str(Path(sys.executable).with_name("ai-docs-kit")), "brand", "parse", "synthetic", "--root", str(root)]

    control = subprocess.run(command, capture_output=True, text=True, timeout=60)

    assert control.returncode == 2
    assert control.stdout.strip() == "no readable PDFs"
    assert control.stderr == ""
    assert manifest.read_bytes() == intact
    damaged = intact[: intact.index(character) + 1]
    manifest.write_bytes(damaged)
    before = {path.relative_to(brand): path.read_bytes() for path in brand.rglob("*") if path.is_file()}

    result = subprocess.run(command, capture_output=True, text=True, timeout=60)

    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    assert str(manifest) in result.stderr
    assert "Traceback" not in result.stderr
    assert len(result.stderr.strip().splitlines()) == 1
    assert manifest.read_bytes() == damaged
    after = {path.relative_to(brand): path.read_bytes() for path in brand.rglob("*") if path.is_file()}
    assert after == before
