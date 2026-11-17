"""A PowerPoint file with no theme part is still read, with a warning, as a Word file is."""

import io
import zipfile
from pathlib import Path

from pptx import Presentation

from ai_docs_kit.brand.templates import read_pptx


def _without_theme() -> bytes:
    buffer = io.BytesIO()
    Presentation().save(buffer)
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as source, zipfile.ZipFile(out, "w") as target:
        for item in source.infolist():
            if not item.filename.startswith("ppt/theme/"):
                target.writestr(item.filename, source.read(item))
    return out.getvalue()


def test_pptx_without_theme_reads_with_a_warning(tmp_path: Path) -> None:
    path = tmp_path / "deck.pptx"
    path.write_bytes(_without_theme())
    facts = read_pptx(path, "deck.pptx")
    assert facts.colours == []
    assert "no theme" in facts.warnings
