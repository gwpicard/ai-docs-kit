"""Atomic replacement shared by working files and their id store."""

import os
import tempfile
from pathlib import Path


def write_atomic(path: Path, text: str) -> None:
    """Replace a text file without exposing a partially written value to readers."""
    handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as temp:
            temp.write(text)
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
