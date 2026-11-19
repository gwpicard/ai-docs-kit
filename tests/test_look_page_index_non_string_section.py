"""A malformed section id in a page index is a CLI input error, not a traceback."""

import json
import subprocess
import sys

from ai_docs_kit.cli import main

SOURCE = """---
doctype: report
format: doc
title: Timing
---

::: {#timing .section intent="body"}
## Timing

Confirm the date before the next meeting.
:::
"""


def test_look_rejects_a_null_section_id_with_exit_two(tmp_path):
    source = tmp_path / "note.md"
    source.write_text(SOURCE, encoding="utf-8")
    assert main(["build", str(source)]) == 0
    version = tmp_path / "note.versions" / "v1"
    index = version / "pages" / "pages.json"
    data = json.loads(index.read_text(encoding="utf-8"))
    data["pages"][0]["sections"] = [None]
    index.write_text(json.dumps(data), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from ai_docs_kit.cli import main; raise SystemExit(main())",
            "look",
            str(version),
            "--pages",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 2, result.stderr
    assert "Traceback" not in result.stderr
    assert "pages.json" in result.stderr and len(result.stderr.strip().splitlines()) == 1
