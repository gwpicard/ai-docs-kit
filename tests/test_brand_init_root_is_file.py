"""A file used as a brand root produces a concise CLI error."""

import subprocess
import sys


def test_brand_init_with_a_file_for_its_root_exits_two(tmp_path):
    root = tmp_path / "brands"
    root.write_text("Keep this file.", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from ai_docs_kit.cli import main; raise SystemExit(main())",
            "brand",
            "init",
            "demo",
            "--root",
            str(root),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 2, result.stderr
    assert "Traceback" not in result.stderr
    assert str(root) in result.stderr and len(result.stderr.strip().splitlines()) == 1
    assert root.read_text(encoding="utf-8") == "Keep this file."
