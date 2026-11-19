import ast
import inspect
import re
import tomllib
import zipfile
from pathlib import Path

import pytest

from ai_docs_kit import cli
from ai_docs_kit.brand.intake import take_in
from ai_docs_kit.checks import bounds, text
from ai_docs_kit.checks.engine import CheckContext
from ai_docs_kit.checks.text import RULES, TerminologyDrift
from ai_docs_kit.model import Document, Item, Section
from ai_docs_kit.theme import neutral_theme

ROOT = Path(__file__).resolve().parent.parent


def _function(name: str) -> ast.FunctionDef:
    tree = ast.parse(inspect.getsource(cli))
    return next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)


def test_pptx_has_no_theme_parameter() -> None:
    assert "theme" not in [a.arg for a in _function("_pptx").args.args]


def test_read_pages_has_no_bare_expression() -> None:
    bare = [n for n in ast.walk(_function("_read_pages")) if isinstance(n, ast.Expr) and not _is_docstring(n)]
    assert bare == []


def _is_docstring(node: ast.Expr) -> bool:
    return isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def test_same_finding_annotations_are_unquoted() -> None:
    for arg in _function("_same_finding").args.args:
        assert not isinstance(arg.annotation, ast.Constant)


def test_look_pages_builds_lines_through_one_helper() -> None:
    source = ast.unparse(_function("_look_pages"))
    assert source.count("', '.join") + source.count('", ".join') == 0


def test_size_noise_constant_is_named() -> None:
    assert bounds._SIZE_NOISE_PT == 1e-6
    assert "1e-6" not in inspect.getsource(bounds).replace("_SIZE_NOISE_PT = 1e-6", "")


def test_text_has_one_blank_safe_hit_helper() -> None:
    assert text._hit("  ", ["anything at all"]) is False
    assert text._hit("", ["anything"]) is False
    assert text._hit("C++", ["we chose c++ today"]) is True
    assert text._hit("cat", ["a dog"]) is False
    assert text._hit("cat", ["a dog", "the Cat"]) is True


def test_an_avoid_term_of_blanks_matches_nothing(tmp_path: Path) -> None:
    (tmp_path / "voice").mkdir()
    (tmp_path / "voice" / "terminology.yaml").write_text("terminology:\n  - preferred: Rust\n    avoid: ['  ']\n")
    theme = neutral_theme().model_copy(update={"root": tmp_path})
    doc = Document(
        front={"title": "T"},
        format="slides",
        sections=[Section(id="s1", intent="bullets", title="T", items=[Item(body="Plain words here.")])],
    )
    rule = next(r for r in RULES if r.id == "source.terminology-drift")
    assert TerminologyDrift().run(CheckContext(doc=doc, theme=theme), rule) == []


@pytest.mark.parametrize("name", ["deck.pptx", "report.docx"])
def test_intake_and_templates_share_the_unreadable_reason(tmp_path: Path, name: str) -> None:
    brand = tmp_path / "acme"
    (brand / "materials" / "templates").mkdir(parents=True)
    with zipfile.ZipFile(brand / "materials" / "templates" / name, "w") as archive:
        archive.writestr("notes.txt", "not an office file")
    assert take_in(brand).files[0].unread == f"{name} is not a readable Office file"


def test_ruff_enables_unused_argument_and_docstring_rules() -> None:
    lint = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["ruff"]["lint"]
    configured = str(lint)
    for code in ("ARG001", "ARG002", "D103"):
        assert code in configured


def test_engine_doc_lists_spoken_for_text_pattern() -> None:
    row = next(
        line for line in (ROOT / "docs" / "ENGINE.md").read_text().splitlines() if line.startswith("| `text-pattern`")
    )
    assert re.search(r"\bspoken\b", row)
