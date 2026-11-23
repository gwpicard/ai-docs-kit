"""A damaged version manifest receives a one-line look error naming the file."""

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


@pytest.mark.parametrize("damaged", ["{", "{}"])
def test_look_names_a_damaged_manifest_in_one_line(tmp_path, damaged):
    source = tmp_path / "note.md"
    source.write_text(
        "---\ndoctype: report\nformat: doc\ntitle: Note\n---\n\n"
        '::: {#timing .section intent="body"}\n## Timing\n\nReply about the plan.\n:::\n',
        encoding="utf-8",
    )
    built = _run("build", source)
    assert built.returncode == 0, built.stderr
    version = tmp_path / "note.versions" / "v1"
    findings = tmp_path / "findings.json"
    findings.write_text("[]", encoding="utf-8")
    args = ("look", version, "--findings", findings)
    control = _run(*args)
    assert control.returncode == 0, control.stderr
    assert "open errors:" in control.stdout
    manifest = version / "manifest.json"
    manifest.write_text(damaged, encoding="utf-8")

    result = _run(*args)

    assert result.returncode == 2, result.stderr
    assert "manifest.json" in result.stderr
    assert "Traceback" not in result.stderr
    assert len(result.stderr.strip().splitlines()) == 1
    assert manifest.read_text(encoding="utf-8") == damaged
