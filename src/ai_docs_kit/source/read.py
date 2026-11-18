from pathlib import Path


def read_source(path: Path, errors: str = "strict") -> str:
    """Read a working file as UTF-8, dropping a leading byte order mark."""
    return path.read_bytes().decode("utf-8-sig", errors=errors)
