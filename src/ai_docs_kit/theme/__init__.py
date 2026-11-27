from pathlib import Path
from typing import NamedTuple

from ai_docs_kit.brand.workspace import BrandError, brand_path, default_root
from ai_docs_kit.source.parser import parse
from ai_docs_kit.source.read import read_source
from ai_docs_kit.theme.loader import ThemeError, load_theme
from ai_docs_kit.theme.models import Theme, to_pt

NEUTRAL_ROOT = Path(__file__).resolve().parent.parent / "themes" / "neutral"

__all__ = ["Theme", "ThemeError", "ThemeResolution", "load_theme", "neutral_theme", "resolve_theme", "to_pt"]


class ThemeResolution(NamedTuple):
    """The selected theme folder and the rule that selected it."""

    path: Path
    rule: str


def resolve_theme(path: Path) -> ThemeResolution:
    """Choose a working file's theme, relative to that file rather than the caller."""
    path = path.absolute()
    doc, _ = parse(read_source(path))
    root = default_root(path.parent)
    brands: dict[str, Path] = {}
    for entry in sorted(root.iterdir()) if root.is_dir() else []:
        try:
            brands[entry.name] = brand_path(entry.name, root) / "theme"
        except BrandError:
            continue
    candidates = ", ".join([*brands, "neutral"])
    if "theme" in doc.front:
        value = doc.front["theme"]
        if isinstance(value, str) and value.strip():
            folder = path.parent / value
            rule = f"front matter theme: {value}"
            if (folder / "theme.yaml").is_file():
                return ThemeResolution(folder.resolve(), rule)
            if value in brands:
                return ThemeResolution(brands[value].resolve(), rule)
            if value == "neutral":
                return ThemeResolution(NEUTRAL_ROOT, rule)
        raise ThemeError(f"{path}: unknown theme: {value!r}; candidates: {candidates}")
    if len(brands) > 1:
        raise ThemeError(f"{path}: theme is missing with several brands; candidates: {candidates}")
    if brands:
        slug, folder = next(iter(brands.items()))
        return ThemeResolution(folder.resolve(), f"single brand: {slug}")
    return ThemeResolution(NEUTRAL_ROOT, "neutral: no theme and no brand")


def neutral_theme() -> Theme:
    """Load the shipped neutral theme."""
    return load_theme(NEUTRAL_ROOT)
