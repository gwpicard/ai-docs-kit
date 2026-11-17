"""The neutral theme's fonts and colours live in `tokens.yaml` only."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
NEUTRAL = ROOT / "src" / "ai_docs_kit" / "themes" / "neutral"
THEME = NEUTRAL / "theme.yaml"


def test_theme_yaml_holds_no_families_or_roles():
    data = yaml.safe_load(THEME.read_text(encoding="utf-8"))
    assert "families" not in (data.get("type") or {}), "theme.yaml still holds type.families"
    assert "roles" not in (data.get("colour") or {}), "theme.yaml still holds colour.roles"
    assert "type" not in data or data["type"], "theme.yaml keeps an empty type block"
    assert "colour" not in data or data["colour"], "theme.yaml keeps an empty colour block"


def test_theme_yaml_drops_the_comment_that_introduced_them():
    text = THEME.read_text(encoding="utf-8")
    for word in ("families", "roles", "test_word_copy"):
        assert word not in text, f"theme.yaml still mentions {word!r}"


def test_word_copy_tests_read_the_expected_values_from_tokens_yaml():
    source = (ROOT / "tests" / "test_word_copy.py").read_text(encoding="utf-8")
    assert "THEME" not in source, "tests/test_word_copy.py still reads theme.yaml"
    assert "theme.yaml" not in source
    assert "tokens.yaml" in source or "TOKENS" in source
