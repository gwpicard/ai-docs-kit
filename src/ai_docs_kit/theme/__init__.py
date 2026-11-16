from pathlib import Path

from ai_docs_kit.theme.loader import ThemeError, load_theme
from ai_docs_kit.theme.models import Theme, to_pt

NEUTRAL_ROOT = Path(__file__).resolve().parent.parent / "themes" / "neutral"

__all__ = ["Theme", "ThemeError", "load_theme", "neutral_theme", "to_pt"]


def neutral_theme() -> Theme:
    """Load the shipped neutral theme, the default until a brand is ingested."""
    return load_theme(NEUTRAL_ROOT)
