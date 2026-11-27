"""Issue 391: the public Python read surface and its command-line JSON contract.

The oracle is the issue's checking recipe, DESIGN.md section 4 and the existing
document, version, page-index and field-index shapes. No new model class names
are prescribed. Result attributes follow those shapes: front/rev/sections,
version/outputs/findings and pngs/pages/fields/findings. Listing functions return
typed lists, as the existing findings and version stores do.
"""

import hashlib
import importlib
import importlib.util
import inspect
import json
import re
import shutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, get_args, get_type_hints

import pytest
import yaml
from PIL import Image
from pydantic import BaseModel, TypeAdapter

from ai_docs_kit import cli
from ai_docs_kit.facts.layout import LayoutFacts
from ai_docs_kit.model import Finding
from ai_docs_kit.render.compose import Composition
from ai_docs_kit.render.marks import FIELD_PATTERN
from ai_docs_kit.source.parser import parse
from ai_docs_kit.store import field_index

ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS = ("read_document", "build", "preview", "list_findings", "list_versions")


def _api() -> ModuleType:
    assert importlib.util.find_spec("ai_docs_kit.api") is not None, "publish the ai_docs_kit.api module"
    api = importlib.import_module("ai_docs_kit.api")
    for name in FUNCTIONS:
        assert callable(getattr(api, name, None)), f"ai_docs_kit.api must export {name}"
    return api


def _call(api, name, *args, **kwargs):
    function = getattr(api, name)
    hints = get_type_hints(function)
    signature = inspect.signature(function)
    for parameter in signature.parameters.values():
        assert parameter.name in hints, f"{name}.{parameter.name} needs a public type annotation"
        assert hints[parameter.name] is not Any
    assert "return" in hints and hints["return"] is not Any, f"{name} needs a typed result"
    result = function(*args, **kwargs)
    assert TypeAdapter(hints["return"]).validate_python(result) == result
    if name.startswith("list_"):
        assert isinstance(result, list), f"{name} returns a typed list"
        assert all(isinstance(item, BaseModel) for item in result)
    else:
        assert isinstance(result, BaseModel), f"{name} returns a Pydantic result"
    return result


def _run(capsys, *args):
    capsys.readouterr()
    try:
        code = cli.main([str(arg) for arg in args])
    except SystemExit as error:
        code = error.code
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.fixture(params=["doc", "slides"])
def working_file(request, tmp_path):
    folder = tmp_path / "project with spaces"
    folder.mkdir()
    name = "report.md" if request.param == "doc" else "deck.md"
    source = folder / name
    shutil.copyfile(ROOT / "tests" / "fixtures" / request.param / name, source)
    return source


def _document(source):
    document, findings = parse(source.read_text(encoding="utf-8"))
    assert not [finding for finding in findings if finding.severity == "error"]
    return document


def _seed_revision(source, tmp_path, capsys):
    # Exercise the person's patch command to create a genuine revision and oplog.
    block = re.search(r"(?ms)^::: \{[^\n]*\}\n.*?^:::$", source.read_text(encoding="utf-8"))
    assert block is not None
    replacement = tmp_path / "replacement.md"
    replacement.write_text(block.group() + "\n", encoding="utf-8")
    first = _document(source).sections[0].id
    code, out, err = _run(capsys, "section", "put", source, first, "--from", replacement)
    assert code == 0, (out, err)
    assert len((source.parent / ".ai_docs_kit" / "oplog.jsonl").read_text().splitlines()) == 1


def _rich_document(source, tmp_path, capsys):
    _seed_revision(source, tmp_path, capsys)
    text = source.read_text(encoding="utf-8")
    # Both ownership values and both lock strengths, with ids in fixture order.
    fences = list(re.finditer(r"(?m)^::: \{[^\n]*\}", text))
    attrs_by_section = (' owner="human" lock="all"', ' owner="ai" lock="text"')
    for fence, attrs in reversed(list(zip(fences[:2], attrs_by_section, strict=True))):
        text = text[: fence.end() - 1] + attrs + text[fence.end() - 1 :]
    text = text.replace("\n---\n", "\naudience: Fixture readers\nlocale: en-GB\ncustom_key: retained\n---\n", 1)
    text = text.replace("## Sources", "## Context\n\nRead-only API acceptance.\n\n## Sources", 1)
    extra = """
::: {#details .section intent="bullets" redraft="Keep the detail"}
## Detail fields

- **First** Original words. [S1 p.2]
  - A nested line.
- Another item. [S1]

A paragraph with café and £ symbols.

> note: Private note.
> spoken: Spoken wording.
> source: Original source line.

```data
categories: [Alpha, Beta]
series:
  - name: Values
    values: [3, 7]
```

```python
print("fixture")
```
:::
"""
    source.write_text(text + extra, encoding="utf-8")
    return _document(source)


def _json(items):
    return [item.model_dump(mode="json") for item in items]


def _snapshot(path):
    """Include directory entries and mtimes so a rewrite or empty version is visible."""
    if not path.exists():
        return None
    paths = [path, *sorted(path.rglob("*"))] if path.is_dir() else [path]
    return {
        str(item.relative_to(path)): (
            item.is_dir(),
            item.stat().st_mtime_ns,
            None if item.is_dir() else hashlib.sha256(item.read_bytes()).hexdigest(),
        )
        for item in paths
    }


def _build_with_cli(source, capsys):
    code, out, err = _run(capsys, "build", source)
    assert code == 0 and not err, (out, err)
    version = Path(out.splitlines()[-1])
    assert version.is_dir()
    return version


def _add_missing_source(source):
    intent = "callout" if _document(source).format == "doc" else "bullets"
    source.write_text(
        source.read_text(encoding="utf-8")
        + f'\n::: {{#missing-source .section intent="{intent}"}}\n## Evidence\n\n- A claim. [S404]\n:::\n',
        encoding="utf-8",
    )


def _check_build(result, source, number):
    assert isinstance(result.version, Path)
    version = source.with_suffix(".versions") / f"v{number}"
    assert result.version == version
    manifest = json.loads((version / "manifest.json").read_bytes())
    assert result.outputs and all(isinstance(output, Path) for output in result.outputs)
    assert {output.name for output in result.outputs} == set(manifest["outputs"])
    assert {output.suffix for output in result.outputs} == {
        ".pdf",
        ".docx" if manifest["format"] == "doc" else ".pptx",
    }
    for output in result.outputs:
        actual = output if output.is_absolute() else version / output
        assert actual.is_file()
        assert actual.read_bytes() == (version / output.name).read_bytes()
    assert _json(result.findings) == json.loads((version / "findings.json").read_bytes())
    assert all(isinstance(finding, Finding) for finding in result.findings)
    return version


def test_read_document_keeps_every_field_and_the_current_revision(working_file, tmp_path, capsys):
    expected = _rich_document(working_file, tmp_path, capsys)
    before = _snapshot(working_file.parent)
    result = _call(_api(), "read_document", working_file)
    expected.rev = 1
    for name in ("front", "format", "context", "sources", "rev", "sections"):
        assert result.model_dump(mode="json")[name] == expected.model_dump(mode="json")[name]
    assert [section.id for section in result.sections] == [section.id for section in expected.sections]
    assert result.sections[0].owner == "human" and result.sections[0].lock == "all"
    assert result.sections[1].owner == "ai" and result.sections[1].lock == "text"
    assert result.sections[-1].data and result.sections[-1].code
    assert result.sections[-1].items[0].citations and result.sections[-1].items[0].sub
    assert _snapshot(working_file.parent) == before


def test_build_findings_and_versions_are_typed_and_read_the_saved_build(working_file, capsys):
    api = _api()
    assert _call(api, "list_versions", working_file) == []
    first = _call(api, "build", working_file)
    v1 = _check_build(first, working_file, 1)
    assert not [finding for finding in first.findings if finding.rule_id == "source.citations-resolve"]
    before = _snapshot(v1)
    _add_missing_source(working_file)
    second = _call(api, "build", working_file)
    v2 = _check_build(second, working_file, 2)
    assert any(
        finding.rule_id == "source.citations-resolve" and finding.section_id == "missing-source"
        for finding in second.findings
    ), "a real source defect must survive in the API result"
    versions = _call(api, "list_versions", working_file)
    assert [(version.number, version.path) for version in versions] == [(1, v1), (2, v2)]
    for version in versions:
        assert version.manifest.model_dump(mode="json") == json.loads((version.path / "manifest.json").read_bytes())
    # A plain CLI build has the same numbering and version-path convention.
    assert _build_with_cli(working_file, capsys) == v2.with_name("v3")
    working_file.unlink()
    assert _json(_call(api, "list_findings", v1)) == _json(first.findings)
    assert _json(_call(api, "list_findings", v2)) == _json(second.findings)
    assert _snapshot(v1) == before


def _assert_index(actual, expected):
    # New optional model fields may appear; every existing layout fact must survive.
    if isinstance(expected, dict):
        assert isinstance(actual, dict)
        for key, value in expected.items():
            assert key in actual
            _assert_index(actual[key], value)
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(actual) == len(expected)
        for item, value in zip(actual, expected, strict=True):
            _assert_index(item, value)
    else:
        assert actual == expected


def _check_preview(result, scratch, version):
    saved = json.loads((version / "pages" / "pages.json").read_bytes())["pages"]
    _assert_index(_json(result.pages), saved)
    facts = LayoutFacts.model_validate_json((version / "layout.json").read_bytes())
    composition = Composition.model_validate_json((version / "composition.json").read_bytes())
    _assert_index(_json(result.fields), field_index(facts, composition))
    assert len(result.pngs) == len(saved) > 1
    assert len(set(result.pngs)) == len(saved), "each page needs its own image"
    for png, page in zip(result.pngs, saved, strict=True):
        assert isinstance(png, Path) and png.resolve().is_relative_to(scratch.resolve())
        assert png.name == page["image"]
        with Image.open(png) as image:
            assert image.format == "PNG" and image.width > 0 and image.height > 0
        assert page["regions"]
    assert _json(result.findings) == json.loads((version / "findings.json").read_bytes())
    known = {section.id for section in composition.sections}
    boxes = [box for page in result.fields for box in page.fields]
    assert boxes and any(box.field == "title" for box in boxes)
    for box in boxes:
        if box.field.startswith("front."):
            assert box.field in {"front.title", "front.audience"}
        else:
            assert box.section in known
            assert FIELD_PATTERN.fullmatch(box.field), box.field
        assert box.w > 0 and box.h > 0
    assert {section for page in result.pages for section in page.sections} == known


def test_build_and_preview_accept_an_explicit_theme(working_file, tmp_path, capsys):
    theme = tmp_path / "synthetic theme"
    shutil.copytree(ROOT / "src" / "ai_docs_kit" / "themes" / "neutral", theme)
    metadata = yaml.safe_load((theme / "theme.yaml").read_text(encoding="utf-8"))
    metadata["name"] = "api-fixture"
    (theme / "theme.yaml").write_text(yaml.safe_dump(metadata), encoding="utf-8")
    rules = theme / "rules" / "authored"
    rules.mkdir(parents=True, exist_ok=True)
    rule = {
        "id": "api.fixture-theme",
        "title": "Identify the explicitly selected theme",
        "origin": "manual",
        "strength": "hard",
        "status": "active",
        "severity": "warning",
        "tier": "source",
        "provenance": {"by": "Synthetic fixture author"},
        "check": {"kind": "text-pattern", "field": "paragraphs", "regex": "."},
        "remedy": {"class": "report", "hint": "Test theme marker"},
    }
    (rules / "marker.yaml").write_text(yaml.safe_dump(rule), encoding="utf-8")
    # The CLI is the oracle for the theme's findings and geometry.
    code, out, err = _run(capsys, "build", working_file, "--theme", theme)
    assert code == 0 and not err, (out, err)
    reference = Path(out.splitlines()[-1])
    expected = json.loads((reference / "findings.json").read_bytes())
    assert any(finding["rule_id"] == "api.fixture-theme" for finding in expected)
    api = _api()
    for name in ("build", "preview"):
        assert inspect.signature(getattr(api, name)).parameters["theme"].default is None
    built = _call(api, "build", working_file, theme=theme)
    version = _check_build(built, working_file, 2)
    assert _json(built.findings) == expected
    assert json.loads((version / "manifest.json").read_bytes())["theme"]["name"] == "api-fixture"
    before = _snapshot(working_file.with_suffix(".versions"))
    scratch = tmp_path / "themed preview"
    preview = _call(api, "preview", working_file, scratch, theme=theme)
    _check_preview(preview, scratch, reference)
    assert _snapshot(working_file.with_suffix(".versions")) == before


@pytest.mark.parametrize("has_versions", [False, True], ids=["no-version-folder", "existing-versions"])
def test_preview_is_a_whole_document_without_writes_and_reuses_layout_facts(
    working_file, tmp_path, capsys, monkeypatch, has_versions
):
    _seed_revision(working_file, tmp_path, capsys)
    if has_versions:
        _add_missing_source(working_file)
        reference = _build_with_cli(working_file, capsys)
        assert any(
            finding["rule_id"] == "source.citations-resolve"
            for finding in json.loads((reference / "findings.json").read_bytes())
        )
    else:
        reference_source = tmp_path / "oracle" / working_file.name
        reference_source.parent.mkdir()
        shutil.copyfile(working_file, reference_source)
        reference = _build_with_cli(reference_source, capsys)
    api = _api()
    versions = working_file.with_suffix(".versions")
    oplog = working_file.parent / ".ai_docs_kit" / "oplog.jsonl"
    paths = (working_file, oplog, versions)
    before = [_snapshot(path) for path in paths]
    scratch = tmp_path / "preview scratch"
    result = _call(api, "preview", working_file, scratch)
    _check_preview(result, scratch, reference)
    assert [_snapshot(path) for path in paths] == before

    # Instrument extraction, not elapsed time or an implementation-specific cache path.
    layout = importlib.import_module("ai_docs_kit.facts.layout")
    extract = layout.layout_facts

    def uncached(*args, **kwargs):
        pytest.fail("the second identical preview must reuse cached layout facts")

    for module in tuple(sys.modules.values()):
        if module is not None and getattr(module, "__name__", "").startswith("ai_docs_kit"):
            for name, value in tuple(vars(module).items()):
                if value is extract:
                    monkeypatch.setattr(module, name, uncached)
    again = _call(api, "preview", working_file, scratch)
    _check_preview(again, scratch, reference)
    assert again.model_dump(mode="json") == result.model_dump(mode="json")
    assert [_snapshot(path) for path in paths] == before


def test_section_list_json_is_the_read_model_and_plain_text_stays_the_same(working_file, tmp_path, capsys):
    document = _rich_document(working_file, tmp_path, capsys)
    lines = []
    for section in document.sections:
        line = f"{section.id}  {section.intent}  {section.owner or '-'}"
        if section.lock:
            line += f"  lock={section.lock}"
        if section.redraft:
            line += f'  redraft="{section.redraft}"'
        lines.append(line)
    code, out, err = _run(capsys, "section", "list", working_file)
    assert code == 0 and not err and out.splitlines() == lines
    code, out, err = _run(capsys, "section", "list", working_file, "--json")
    assert code == 0 and not err, (out, err)
    result = _call(_api(), "read_document", working_file)
    assert type(result).model_validate_json(out) == result
    assert json.loads(out) == result.model_dump(mode="json")


def test_build_json_is_the_build_model_and_plain_text_stays_the_same(working_file, capsys):
    first = _build_with_cli(working_file, capsys)
    code, out, err = _run(capsys, "build", working_file, "--json")
    assert code == 0 and not err, (out, err)
    raw = json.loads(out)  # A single JSON value, without progress lines.
    api = _api()
    result_type = get_type_hints(api.build)["return"]
    result = TypeAdapter(result_type).validate_python(raw)
    _check_build(result, working_file, 2)
    assert result.model_dump(mode="json") == raw
    assert _json(_call(api, "list_findings", result.version)) == _json(result.findings)
    code, out, err = _run(capsys, "build", working_file)
    manifest = json.loads((first / "manifest.json").read_bytes())
    findings = json.loads((first / "findings.json").read_bytes())
    errors = [
        f"{finding['severity']} {finding['rule_id']} {finding['section_id'] or '-'} {finding['message']}"
        for finding in findings
        if finding["severity"] == "error"
    ]
    gaps = [f"gap {gap['section'] or '-'}: {gap['text']}" for gap in manifest["gaps"]]
    assert code == 0 and not err
    assert out.splitlines() == [
        str(working_file.parent / "build" / f"{working_file.stem}.pdf"),
        *errors,
        *gaps,
        str(first.with_name("v3")),
    ]
    # Error findings must stay inside the JSON result, too.
    _add_missing_source(working_file)
    code, out, err = _run(capsys, "build", working_file, "--json")
    assert code == 0 and not err, (out, err)
    defective = TypeAdapter(result_type).validate_json(out)
    _check_build(defective, working_file, 4)
    assert any(finding.rule_id == "source.citations-resolve" for finding in defective.findings)


def test_look_pages_json_uses_the_preview_model_and_keeps_plain_text(working_file, tmp_path, capsys):
    _add_missing_source(working_file)
    version = _build_with_cli(working_file, capsys)
    pages = json.loads((version / "pages" / "pages.json").read_bytes())["pages"]
    findings = json.loads((version / "findings.json").read_bytes())
    assert any(finding["rule_id"] == "source.citations-resolve" for finding in findings)
    expected = []
    for page in pages:
        front_fields = dict.fromkeys(
            region["field"] for region in page["regions"] if region.get("field", "").startswith("front.")
        )
        suffix = f"; {', '.join(front_fields)}" if front_fields else ""
        expected.append(f"page {page['page']}: {', '.join(page['sections'])}{suffix}")
    expected += ["engine findings (do not repeat):"]
    expected += [
        f"- {f['rule_id']} {f['severity']} page {f['page']} section {f['section_id']}: {f['message']}" for f in findings
    ]
    code, out, err = _run(capsys, "look", version, "--pages")
    assert code == 0 and not err and out.splitlines() == expected
    before = _snapshot(version)
    code, out, err = _run(capsys, "look", version, "--pages", "--json")
    assert code == 0 and not err, (out, err)
    preview = _call(_api(), "preview", working_file, tmp_path / "scratch")
    result = type(preview).model_validate_json(out)
    _check_preview(result, version, version)
    assert result.pages == preview.pages and result.fields == preview.fields
    assert result.findings == preview.findings
    assert result.model_dump(mode="json") == json.loads(out)
    assert _snapshot(version) == before


def _result_models(annotation):
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return {annotation}
    return {model for argument in get_args(annotation) for model in _result_models(argument)}


def test_each_result_model_has_a_current_committed_json_schema():
    api = _api()
    models = set()
    for name in FUNCTIONS:
        hints = get_type_hints(getattr(api, name))
        assert "return" in hints, f"{name} must name its result model"
        result_models = _result_models(hints["return"])
        assert result_models, f"{name} must return a Pydantic model or a list of models"
        models.update(result_models)
    directory = ROOT / "docs" / "schemas" / "api"
    assert directory.is_dir(), "commit the public result schemas under docs/schemas/api/"
    paths = {path.name: path for path in directory.glob("*.schema.json")}
    for model in models:
        name = f"{model.__name__}.schema.json"
        assert name in paths, f"missing schema export for {model.__name__}"
        assert json.loads(paths[name].read_bytes()) == model.model_json_schema(), f"regenerate {name}"


def test_plan_records_the_python_api_under_surfaces():
    text = (ROOT / "PLAN.md").read_text(encoding="utf-8")
    surfaces = text.split("## Surfaces\n", 1)[1].split("\n## ", 1)[0]
    assert "ai_docs_kit.api" in surfaces, "list the public Python API under PLAN.md's Surfaces"
    assert re.search(r"python", surfaces, re.IGNORECASE), "identify the surface as a Python API"
