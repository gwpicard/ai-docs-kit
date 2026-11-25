"""Files occupying build subfolders receive the same clean refusal as a blocked output folder."""

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


@pytest.mark.parametrize("blocked", ["render", "look"])
def test_build_reports_an_internal_path_collision_cleanly(tmp_path, blocked):
    source = tmp_path / "note.md"
    source.write_text(
        "---\ndoctype: report\nformat: doc\ntitle: Note\n---\n\n"
        '::: {#timing .section intent="body"}\n## Timing\n\nReply about the plan.\n:::\n',
        encoding="utf-8",
    )
    control = _run("build", source, "--out", tmp_path / "good")
    assert control.returncode == 0, control.stderr
    out = tmp_path / "blocked"
    out.mkdir()
    blocker = out / blocked
    blocker.write_text("Keep this file.\n", encoding="utf-8")
    before_source, before_blocker = source.read_bytes(), blocker.read_bytes()

    result = _run("build", source, "--out", out)

    assert result.returncode == 2, result.stderr
    assert str(blocker) in result.stderr
    assert "Traceback" not in result.stderr
    assert len(result.stderr.strip().splitlines()) == 1
    assert source.read_bytes() == before_source
    assert blocker.read_bytes() == before_blocker
    assert not (tmp_path / "note.versions" / "v2").exists()
