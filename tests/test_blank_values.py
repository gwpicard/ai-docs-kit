"""A blank or whitespace-only value in a file a person or agent writes is refused where the file is read."""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import BaseModel, ValidationError

from ai_docs_kit.cli import main
from ai_docs_kit.model.rules import Provenance, Remedy, Rule, Scope
from ai_docs_kit.review.plan import CommentItem, Emphasis, ReviewPlan, SectionPlan, StructureItem, Warning
from ai_docs_kit.store import LookFinding
from ai_docs_kit.theme import NEUTRAL_ROOT
from ai_docs_kit.theme.voice import Term, Voice

BLANKS = ["", "   ", "\t\n"]

RULE: dict[str, Any] = {
    "id": "feedback.dates",
    "title": "Give a date",
    "origin": "feedback",
    "strength": "soft",
    "status": "proposed",
    "severity": "error",
    "tier": "source",
    "check": {"kind": "text-pattern", "field": "paragraphs", "regex": "ASAP"},
    "remedy": {"class": "redraft", "hint": "Give a date instead."},
    "provenance": {"label": "answered", "source": {"comment": "No."}, "by": "Dana"},
}
LOOK = {"severity": "warning", "rule": "look.crowded", "page": 1, "section": "s1", "message": "Too tight."}
COMMENT = {"author": "Dana", "text": "Reword.", "anchor": "words"}

# (model, valid input, path to the field that must refuse a blank)
CASES: list[tuple[type[BaseModel], dict[str, Any], tuple[Any, ...]]] = [
    (Rule, RULE, ("id",)),
    (Rule, RULE, ("title",)),
    (Rule, RULE, ("remedy", "hint")),
    (Rule, RULE, ("provenance", "by")),
    (Remedy, RULE["remedy"], ("hint",)),
    (Provenance, RULE["provenance"], ("by",)),
    (Scope, {"roles": ["title"], "components": ["card"], "intents": ["body"]}, ("roles", 0)),
    (Scope, {"roles": ["title"], "components": ["card"], "intents": ["body"]}, ("components", 0)),
    (Scope, {"roles": ["title"], "components": ["card"], "intents": ["body"]}, ("intents", 0)),
    (LookFinding, LOOK, ("rule",)),
    (LookFinding, LOOK, ("message",)),
    (LookFinding, LOOK, ("section",)),
    (Term, {"preferred": "use", "avoid": ["utilise"]}, ("preferred",)),
    (Term, {"preferred": "use", "avoid": ["utilise"]}, ("avoid", 0)),
    (Voice, {"banned": ["synergy"]}, ("banned", 0)),
    (Voice, {"summary": {"doc": "Plain."}}, ("summary", "doc")),
    (Voice, {"terminology": [{"preferred": "use", "avoid": ["utilise"]}]}, ("terminology", 0, "preferred")),
    (Voice, {"terminology": [{"preferred": "use", "avoid": ["utilise"]}]}, ("terminology", 0, "avoid", 0)),
    (CommentItem, COMMENT | {"action": "apply", "proposal": "New words."}, ("proposal",)),
    (CommentItem, COMMENT | {"action": "redraft", "ask": "Say it shorter."}, ("ask",)),
]


def _with(data: dict[str, Any], path: tuple[Any, ...], value: str) -> dict[str, Any]:
    out = json.loads(json.dumps(data))
    node: Any = out
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return out


@pytest.mark.parametrize("blank", BLANKS, ids=["empty", "spaces", "tab-newline"])
@pytest.mark.parametrize(
    "model, valid, path", CASES, ids=lambda x: ".".join(map(str, x)) if isinstance(x, tuple) else ""
)
def test_a_blank_value_is_refused_and_the_error_names_the_field(model, valid, path, blank):
    model.model_validate(valid)
    with pytest.raises(ValidationError) as caught:
        model.model_validate(_with(valid, path, blank))
    assert any(tuple(e["loc"][-len(path) :]) == path for e in caught.value.errors()), caught.value.errors()


# --- the commands that read the files: exit 2 with one line naming the field ---


def _one_line_error(capsys, tmp_path: Path, field: str) -> None:
    err = capsys.readouterr().err.strip()
    assert len(err.splitlines()) == 1, err
    # The temporary folder is named after the test, so leave it out when looking for the field name.
    assert field in err.replace(str(tmp_path.resolve()), "").replace(str(tmp_path), ""), err


@pytest.mark.parametrize(
    "change, field",
    [
        (lambda r: r.update(title="  "), "title"),
        (lambda r: r["remedy"].update(hint=""), "hint"),
        (lambda r: r.update(id="\t"), "id"),
    ],
    ids=["title", "hint", "id"],
)
def test_rule_test_refuses_a_blank_rule_field_with_one_line(tmp_path, capsys, change, field):
    rule = json.loads(json.dumps(RULE))
    change(rule)
    path = tmp_path / "rule.yaml"
    path.write_text(yaml.safe_dump(rule), encoding="utf-8")
    assert main(["rule", "test", str(path), "--example", f"{tmp_path}/v1/s1"]) == 2
    _one_line_error(capsys, tmp_path, field)


@pytest.mark.parametrize(
    "terminology, field",
    [
        ("banned: ['']\n", "banned"),
        ("banned: ['   ']\n", "banned"),
        ("terminology: [{preferred: use, avoid: [' ']}]\n", "avoid"),
        ("terminology: [{preferred: '  ', avoid: [utilise]}]\n", "preferred"),
    ],
    ids=["banned-empty", "banned-spaces", "avoid-spaces", "preferred-spaces"],
)
@pytest.mark.parametrize("command", ["build", "check"])
def test_a_blank_terminology_entry_is_exit_2_with_one_line(tmp_path, capsys, terminology, field, command):
    theme = tmp_path / "theme"
    shutil.copytree(NEUTRAL_ROOT, theme)
    (theme / "voice").mkdir(exist_ok=True)
    (theme / "voice" / "terminology.yaml").write_text(terminology, encoding="utf-8")
    work = tmp_path / "note.md"
    shutil.copyfile(Path(__file__).parent / "fixtures" / "doc" / "report.md", work)
    assert main([command, str(work), "--theme", str(theme)]) == 2
    _one_line_error(capsys, tmp_path, field)


@pytest.mark.parametrize("field, action", [("proposal", "apply"), ("ask", "redraft")])
def test_review_apply_refuses_a_blank_decision_with_one_line(tmp_path, capsys, field, action):
    work = tmp_path / "report.md"
    shutil.copyfile(Path(__file__).parent / "fixtures" / "doc" / "report.md", work)
    item = COMMENT | {"accepted": True, "action": action, field: "   "}
    plan = {
        "version": 1,
        "review_copy": "r.docx",
        "sections": {"s1": {"wording": None, "owner": None, "confirm": [item]}},
    }
    path = tmp_path / "decided.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    assert main(["review", "apply", str(work), "--plan", str(path)]) == 2
    _one_line_error(capsys, tmp_path, field)


# --- the architecture test ---

MODELS: list[type[BaseModel]] = [
    Rule,
    Remedy,
    Provenance,
    Scope,
    LookFinding,
    Term,
    Voice,
    ReviewPlan,
    SectionPlan,
    CommentItem,
    StructureItem,
    Emphasis,
    Warning,
]

# "Model.field": why a blank is allowed. Everything else needs a constraint.
ALLOWED_BLANK: dict[str, str] = {
    "CommentItem.author": "Word and PowerPoint name no author when the file has none; `review read` writes it",
    "CommentItem.id": "copied from the Office file by `review read`, not typed",
    "CommentItem.reply_to": "copied from the Office file by `review read`, not typed",
    "CommentItem.text": "a comment's words are copied by `review read`; an empty comment is a real one",
    "CommentItem.anchor": "the commented words are copied by `review read`; a range can be empty",
    "CommentItem.spans": "section ids written by `review read`",
    "CommentItem.shape": "a shape name copied from the deck by `review read`",
    "Emphasis.text": "emphasised words copied by `review read`",
    "Emphasis.value": "a colour hex copied by `review read`",
    "SectionPlan.wording": "the wording copied by `review read`; a reviewer may empty a section",
    "SectionPlan.items": "list items copied by `review read`; a reviewer may empty an item",
    "SectionPlan.fields": "field text copied by `review read`; a reviewer may empty a field",
    "StructureItem.text": "unplaced text copied by `review read`",
    "StructureItem.section": "section ids written by `review read`",
    "StructureItem.after": "section ids written by `review read`",
    "StructureItem.author": "copied from the Office file by `review read`",
    "StructureItem.order": "section ids written by `review read`",
    "Warning.code": "written by `review read`, not by a person",
    "Warning.message": "written by `review read`, not by a person",
    "ReviewPlan.review_copy": "the file name `review read` was given",
}


def _string_leaves(node: dict[str, Any]) -> list[dict[str, Any]]:
    """The plain string schemas inside a field: itself, its union members, list items and dict values."""
    if "$ref" in node:
        return []
    found: list[dict[str, Any]] = []
    for part in node.get("anyOf", []) + node.get("allOf", []):
        found += _string_leaves(part)
    if "items" in node:
        found += _string_leaves(node["items"])
    if isinstance(node.get("additionalProperties"), dict):
        found += _string_leaves(node["additionalProperties"])
    if node.get("type") == "string" and not {"enum", "const", "format"} & node.keys():
        found.append(node)
    return found


def _unconstrained() -> set[str]:
    names: set[str] = set()
    for model in MODELS:
        schema = model.model_json_schema()
        for def_name, body in {model.__name__: schema, **schema.get("$defs", {})}.items():
            if def_name not in {m.__name__ for m in MODELS}:
                continue
            for field, prop in body.get("properties", {}).items():
                if any(leaf.get("minLength", 0) < 1 and "pattern" not in leaf for leaf in _string_leaves(prop)):
                    names.add(f"{def_name}.{field}")
    return names


def test_every_str_field_refuses_a_blank_unless_it_is_allowed():
    missing = sorted(_unconstrained() - ALLOWED_BLANK.keys())
    assert not missing, f"str fields with no blank check and no allowlist reason: {missing}"


def test_the_allowlist_names_only_fields_that_exist_and_need_it():
    stale = sorted(ALLOWED_BLANK.keys() - _unconstrained())
    assert not stale, f"allowlisted fields that are already constrained or do not exist: {stale}"
