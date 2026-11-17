"""Leave tests/fixtures as the run found it (issue 33).

Builds write `<stem>.versions/vN` next to their source, and some locked tests build
fixtures in place. After the session, remove every path under tests/fixtures that
was not there at the start; paths that existed before stay untouched.
"""

import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _paths() -> set[Path]:
    return set(FIXTURES.rglob("*"))


@pytest.fixture(scope="session", autouse=True)
def fixtures_left_unchanged():
    before = _paths()
    yield
    # Shallowest first, so a new folder goes with everything inside it.
    for path in sorted(_paths() - before, key=lambda p: len(p.parts)):
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
        except FileNotFoundError:
            pass  # already gone, for instance removed with its parent folder
        except OSError as error:
            raise RuntimeError(f"could not remove {path}: {error}") from error
