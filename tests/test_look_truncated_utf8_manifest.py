"""Look names a manifest truncated inside a UTF-8 character without changing it."""

import json
import subprocess
import sys
from pathlib import Path


def _run(*args):
    return subprocess.run(
        [str(Path(sys.executable).with_name("ai-docs-kit")), *map(str, args)],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_look_refuses_a_manifest_truncated_inside_a_utf8_character(tmp_path):
    source = tmp_path / "note.md"
    source.write_text(
        "---\ndoctype: report\nformat: doc\ntitle: Note\n---\n\n"
        '::: {#timing .section intent="body"}\n## Timing\n\nReply about the plan.\n:::\n',
        encoding="utf-8",
    )
    built = _run("build", source)
    assert built.returncode == 0, built.stderr
    version = tmp_path / "note.versions" / "v1"
    manifest = version / "manifest.json"
    data = json.loads(manifest.read_bytes())
    data["written"] = "café"
    manifest.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    findings = tmp_path / "findings.json"
    findings.write_text("[]", encoding="utf-8")
    args = ("look", version, "--findings", findings)

    control = _run(*args)

    assert control.returncode == 0, control.stderr
    assert "open errors:" in control.stdout
    intact = manifest.read_bytes()
    character = "é".encode()
    assert character in intact
    damaged = intact[: intact.index(character) + 1]
    manifest.write_bytes(damaged)
    before = {path.relative_to(version): path.read_bytes() for path in version.rglob("*") if path.is_file()}

    result = _run(*args)

    assert result.returncode == 2, result.stderr
    assert str(manifest) in result.stderr
    assert "not valid manifest" in result.stderr
    assert "Traceback" not in result.stderr
    assert len(result.stderr.strip().splitlines()) == 1
    assert result.stdout == ""
    assert manifest.read_bytes() == damaged
    after = {path.relative_to(version): path.read_bytes() for path in version.rglob("*") if path.is_file()}
    assert after == before
