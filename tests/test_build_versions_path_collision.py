"""A file at the versions folder path produces a clean build failure."""

import subprocess
import sys
from pathlib import Path


def test_build_reports_a_versions_path_collision_without_a_traceback(tmp_path):
    source = tmp_path / "note.md"
    source.write_text(
        "---\ndoctype: report\nformat: doc\ntitle: Timing\n---\n\n"
        '::: {#timing .section intent="body"}\n## Timing\n\nReply about the plan.\n:::\n',
        encoding="utf-8",
    )
    blocker = tmp_path / "note.versions"
    blocker.write_text("A file already occupies this path.\n", encoding="utf-8")
    before = source.read_bytes(), blocker.read_bytes()

    result = subprocess.run(
        [str(Path(sys.executable).with_name("ai-docs-kit")), "build", str(source)],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 2, result.stderr
    assert "note.versions" in result.stderr
    assert "Traceback" not in result.stderr
    assert len(result.stderr.strip().splitlines()) == 1
    assert (source.read_bytes(), blocker.read_bytes()) == before
