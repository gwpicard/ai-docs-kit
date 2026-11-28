"""Issue 375: a person's edits use the public API and the locked patch path.

Oracles: the issue's checking recipe, PLAN.md's human-wording decision,
ENGINE.md sections 5.3 and 13.3, and source/files.py from issue 373.
Result class names are open; their fields are rev and section. A deletion
returns the removed section. CLI JSON uses rev and section_id.
"""

import fcntl
import inspect
import json
import os
import shutil
from pathlib import Path
from typing import Any, get_type_hints

import pytest
from pydantic import BaseModel, TypeAdapter

from ai_docs_kit import api, cli
from ai_docs_kit.api import models
from ai_docs_kit.model import Section
from ai_docs_kit.source import files

ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS = ("edit_fields", "add_section", "delete_section", "move_section")


def _function(name):
    function = getattr(api, name, None)
    assert callable(function), f"ai_docs_kit.api must publish {name}"
    return function


def _call(name, *args, **kwargs):
    function = _function(name)
    hints = get_type_hints(function)
    for parameter in inspect.signature(function).parameters:
        assert parameter in hints and hints[parameter] is not Any, f"type {name}.{parameter}"
    assert "return" in hints and hints["return"] is not Any, f"type {name}'s result"
    result = function(*args, **kwargs)
    assert isinstance(result, BaseModel), "edit results must be typed models"
    assert TypeAdapter(hints["return"]).validate_python(result) == result
    assert isinstance(result.rev, int) and isinstance(result.section, Section)
    return result


def _run(capsys, *args):
    capsys.readouterr()
    try:
        code = cli.main([str(arg) for arg in args])
    except SystemExit as error:
        code = error.code
    output = capsys.readouterr()
    return code, output.out, output.err


def _working(tmp_path, reverse=False, format_="doc", lock=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "survey note.md"
    shutil.copyfile(ROOT / "tests/fixtures/section-put-fact-guard/working.md", path)
    front, first = path.read_text(encoding="utf-8").split("::: ", 1)
    first = "::: " + first.replace("## Findings\n", "## Findings\n\nThe scope is agreed.\n")
    if lock:
        first = first.replace('intent="body"', f'intent="body" lock="{lock}"')
    sections = [first] + [
        f'::: {{#{key} .section intent="body"}}\n## {title}\n\n{words}\n:::\n'
        for key, title, words in (
            ("other", "Context", "The remaining wording stays."),
            ("last", "Conclusion", "The final wording stays."),
        )
    ]
    if reverse:
        sections.reverse()
    text = front.replace("format: doc", f"format: {format_}") + "\n".join(sections)
    if format_ == "slides":
        text = text.replace('intent="body"', 'intent="statement"')
    path.write_text(text, encoding="utf-8")
    return path


def _sections(path):
    return {section.id: section for section in api.read_document(path).sections}


def _entries(path):
    log = path.parent / ".ai_docs_kit/oplog.jsonl"
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def _snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def _invoke(name, path, rev, section_id="findings", after_id="other"):
    if name == "edit_fields":
        return _function(name)(path, section_id, {"paragraphs": ["A person's changed wording."]}, rev)
    if name == "add_section":
        return _function(name)(path, after_id, Section(intent="body", paragraphs=["An added section."]), rev)
    if name == "move_section":
        return _function(name)(path, section_id, after_id, rev)
    return _function(name)(path, section_id, rev)


def _typed_error(call, code):
    with pytest.raises(Exception) as caught:
        call()
    error = caught.value
    assert type(error) not in (Exception, ValueError, TypeError, KeyError), "raise a typed edit refusal"
    assert getattr(error, "code", None) == code
    assert isinstance(getattr(error, "message", None), str) and error.message.strip()
    return error


@pytest.mark.parametrize("reverse", [False, True], ids=["forward", "reversed"])
def test_each_edit_writes_one_human_patch_under_the_project_lock(tmp_path, monkeypatch, reverse):
    path = _working(tmp_path, reverse)
    original = api.read_document(path)
    untouched = _sections(path)
    writes = []
    write_atomic = files._write_atomic

    def observed_write(target, text):
        descriptor = os.open(path.parent / ".ai_docs_kit", os.O_RDONLY)
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(descriptor)
        writes.append(target)
        return write_atomic(target, text)

    monkeypatch.setattr(files, "_write_atomic", observed_write)
    edited = _call("edit_fields", str(path), "findings", {"title": "Revised finding", "note": "Keep my words."}, 0)
    assert edited.rev == 1 and edited.section.id == "findings"
    assert edited.section.title == "Revised finding" and edited.section.note == "Keep my words."
    assert edited.section.owner == "human"
    assert edited.section == _sections(path)["findings"]
    for key in ("other", "last"):
        assert _sections(path)[key] == untouched[key]
    edited_state = _sections(path)

    added_input = Section(intent="body", title="Added", paragraphs=["The person's added wording."])
    added = _call("add_section", path, "findings", added_input, edited.rev)
    added_id = added.section.id
    assert added.rev == 2 and added_id and added_id not in untouched
    assert added.section.paragraphs == added_input.paragraphs and added_input.id is None
    assert added.section.title == added_input.title
    assert _sections(path) == {**edited_state, added_id: added.section}
    order = [section.id for section in api.read_document(path).sections]
    assert order.index(added_id) == order.index("findings") + 1
    prior = _sections(path)
    moved = _call("move_section", path, added_id, "last", added.rev)
    assert moved.rev == 3 and moved.section == prior[added_id]
    order = [section.id for section in api.read_document(path).sections]
    assert order.index(added_id) == order.index("last") + 1
    assert _sections(path) == prior
    deleted = _call("delete_section", path, added_id, moved.rev)
    assert deleted.rev == 4 and deleted.section == prior[added_id]
    assert _sections(path) == {key: value for key, value in prior.items() if key != added_id}
    final = api.read_document(path)
    assert final.rev == 4
    assert (final.front, final.context, final.sources) == (original.front, original.context, original.sources)
    assert [section.id for section in final.sections] == [section.id for section in original.sections]
    entries = _entries(path)
    assert writes == [path] * 4, "each public edit must write through the locked patch path once"
    assert [entry["rev"] for entry in entries] == [1, 2, 3, 4]
    assert [entry["author"] for entry in entries] == ["human"] * 4
    for entry, expected in zip(entries, ("set_fields", "insert_after", "move_section", "delete_section"), strict=True):
        assert expected in {op["op"] for op in entry["ops"]}
        assert entry["file"] == path.name


@pytest.mark.parametrize(
    ("name", "code"),
    [
        (name, code)
        for name in FUNCTIONS
        for code in ("stale-base-rev", "unknown-section", "lock-all")
        if not (name == "add_section" and code == "lock-all")
    ],
)
def test_refused_public_edits_leave_the_working_file_and_history_unchanged(tmp_path, capsys, name, code):
    path = _working(tmp_path, lock="all" if code == "lock-all" else None)
    if code == "stale-base-rev":
        block = tmp_path / "replacement.md"
        block.write_text(
            '::: {#findings .section intent="body"}\n## Findings\n\nThe scope is agreed.\n:::\n',
            encoding="utf-8",
        )
        result, out, err = _run(capsys, "section", "put", path, "findings", "--from", block)
        assert result == 0, (out, err)
    before = _snapshot(tmp_path)
    _function(name)  # Missing API functions must fail by assertion, outside raises.
    section_id = "absent" if code == "unknown-section" else "findings"
    after_id = "absent" if name == "add_section" and code == "unknown-section" else "other"
    _typed_error(lambda: _invoke(name, path, 0, section_id, after_id), code)
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize(("format_", "hyphen_first"), [("doc", True), ("slides", False)])
def test_edit_read_build_round_trip_keeps_unsupported_human_text_byte_for_byte(tmp_path, capsys, format_, hyphen_first):
    path = _working(tmp_path, format_=format_)
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "the EU survey was completed in 2024.", "https://example.invalid/survey"
        ),
        encoding="utf-8",
    )
    incoming = tmp_path / "gathered.json"
    incoming.write_text(json.dumps([{"text": "The reading is 12.", "source": "S1"}]), encoding="utf-8")
    code, out, err = _run(capsys, "facts", "add", path, incoming)
    assert code == 0, (out, err)
    original = _sections(path)
    paragraphs = ["- the reading is 987. [S1]", "The person's café wording stays: £ and \\q."]
    if not hyphen_first:
        paragraphs.reverse()
    result = _call("edit_fields", path, "findings", {"paragraphs": paragraphs}, 0)
    assert result.rev == 1 and result.section.owner == "human"
    assert result.section.paragraphs == paragraphs, "a person's new figure must bypass the fact guard"
    read = api.read_document(path)
    assert read.rev == result.rev
    assert _sections(path)["findings"].paragraphs == paragraphs
    assert _sections(path)["findings"].items == [], "a leading hyphen must remain paragraph text"
    for key in ("other", "last"):
        assert _sections(path)[key] == original[key]
    saved = path.read_bytes()
    code, out, err = _run(capsys, "build", path)
    assert code == 0, (out, err)
    assert path.read_bytes() == saved
    version = Path(out.splitlines()[-1])
    composition = json.loads((version / "composition.json").read_bytes())
    section = next(section for section in composition["sections"] if section["id"] == "findings")
    assert [text.encode("utf-8") for text in section["props"]["paragraphs"]] == [p.encode("utf-8") for p in paragraphs]
    assert _sections(path)["findings"].owner == "human"
    findings = json.loads((version / "findings.json").read_bytes())
    unsupported = [finding for finding in findings if finding["rule_id"] == "source.number-in-source"]
    assert len(unsupported) == 1 and unsupported[0]["section_id"] == "findings"
    assert unsupported[0]["measured"]["number"] == "987"


def test_edit_results_and_typed_error_payloads_have_current_exported_schema_pins(tmp_path):
    path = _working(tmp_path)
    results = [_call("edit_fields", path, "findings", {"title": "Revised"}, 0)]
    results.append(_call("add_section", path, "other", Section(intent="body", paragraphs=["Added wording."]), 1))
    added_id = results[-1].section.id
    results.append(_call("move_section", path, added_id, "last", 2))
    results.append(_call("delete_section", path, added_id, 3))
    errors = [
        _typed_error(lambda: _invoke("edit_fields", path, 0), "stale-base-rev"),
        _typed_error(lambda: _invoke("edit_fields", path, 4, "absent"), "unknown-section"),
    ]
    locked = _working(tmp_path / "locked", lock="all")
    errors.append(_typed_error(lambda: _invoke("edit_fields", locked, 0), "lock-all"))
    exported = tmp_path / "schemas"
    api.export_api_schemas(exported)
    public_models = {
        value
        for namespace in (vars(api), vars(models))
        for value in namespace.values()
        if isinstance(value, type) and issubclass(value, BaseModel)
    }
    error_models = [model for model in public_models if {"code", "message"} <= set(model.model_fields)]
    assert error_models, "publish a typed edit error payload with code and message"
    for error in errors:
        payload = {"code": error.code, "message": error.message}
        assert any(model.model_validate(payload).code == error.code for model in error_models)
    for model in {type(result) for result in results} | set(error_models):
        name = f"{model.__name__}.schema.json"
        pinned = ROOT / "docs/schemas/api" / name
        assert pinned.is_file(), f"pin {name} under docs/schemas/api/"
        assert json.loads(pinned.read_bytes()) == model.model_json_schema()
        assert (exported / name).is_file(), f"export_api_schemas must include {name}"
        assert json.loads((exported / name).read_bytes()) == json.loads(pinned.read_bytes())


def test_section_put_json_reports_each_new_revision_and_section_id(tmp_path, capsys):
    path = _working(tmp_path)
    replacement = tmp_path / "replacement.md"
    for revision, words in enumerate(("The scope is agreed.", "The scope remains agreed."), start=1):
        replacement.write_text(
            f'::: {{#findings .section intent="body"}}\n## Findings\n\n{words}\n:::\n', encoding="utf-8"
        )
        code, out, err = _run(capsys, "section", "put", path, "findings", "--from", replacement, "--json")
        assert code == 0, (out, err)
        assert not err
        payload = json.loads(out)
        assert payload["rev"] == revision and payload["section_id"] == "findings"
        assert api.read_document(path).rev == revision
        assert _sections(path)["findings"].paragraphs == [words]
        assert len(_entries(path)) == revision
