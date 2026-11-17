"""A review copy is compared with the version it was built from, named by a document property."""

import json
import zipfile
from pathlib import Path

import pytest
from lxml import etree
from tests.support.fixtures import fixture_path

from ai_docs_kit.cli import main

PROPERTY = "ai-docs-kit-version"
CUSTOM = "docProps/custom.xml"

DOC = """---
doctype: report
format: doc
title: Note
---

::: {#alpha01 .section intent="body"}
## Alpha

Alpha keeps its original wording here.
:::
"""

KINDS = {
    "docx": ("report", "report.md"),
    "pptx": ("deck", "deck.md"),
}


def _source(kind: str) -> str:
    if kind == "docx":
        return DOC
    return fixture_path("slides", "deck.md").read_text(encoding="utf-8")


def _built_twice(tmp_path: Path, kind: str) -> Path:
    stem, name = KINDS[kind]
    (tmp_path / name).write_text(_source(kind), encoding="utf-8")
    assert main(["build", str(tmp_path / name)]) == 0
    assert main(["build", str(tmp_path / name)]) == 0
    folder = tmp_path / f"{stem}.versions"
    assert (folder / "v1").is_dir() and (folder / "v2").is_dir()
    return folder


def _property(path: Path) -> str | None:
    with zipfile.ZipFile(path) as archive:
        if CUSTOM not in archive.namelist():
            return None
        root = etree.fromstring(archive.read(CUSTOM))
    for node in root:
        if node.get("name") == PROPERTY:
            return "".join(node.itertext()).strip()
    return None


def _rewrite(source: Path, target: Path, value: str | None) -> None:
    """Copy `source` to `target` with the version property set to `value`, or removed when `None`."""
    with zipfile.ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    if value is not None:
        assert CUSTOM in parts, f"{source} has no custom properties to change"
    root = etree.fromstring(parts[CUSTOM]) if CUSTOM in parts else etree.Element("Properties")
    for node in list(root):
        if node.get("name") == PROPERTY:
            if value is None:
                root.remove(node)
            else:
                for child in node:
                    child.text = value
    if CUSTOM in parts:
        parts[CUSTOM] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)


def _read(copy: Path, folder: Path, version: int) -> tuple[int, dict]:
    code = main(["review", "read", str(copy)])
    plans = list(folder.glob("v*/review-plan.json"))
    if code != 0 or not plans:
        return code, {}
    path = folder / f"v{version}" / "review-plan.json"
    return code, json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("kind", ["docx", "pptx"])
def test_every_build_records_its_version_number(tmp_path, kind):
    folder = _built_twice(tmp_path, kind)
    stem = KINDS[kind][0]
    for number in (1, 2):
        assert _property(folder / f"v{number}" / f"{stem}.{kind}") == str(number)


@pytest.mark.parametrize("kind", ["docx", "pptx"])
def test_copy_of_version_one_is_compared_with_version_one_and_none_is_sent(tmp_path, kind):
    folder = _built_twice(tmp_path, kind)
    stem = KINDS[kind][0]
    copy = tmp_path / f"{stem}-reviewed.{kind}"
    copy.write_bytes((folder / "v1" / f"{stem}.{kind}").read_bytes())
    code, plan = _read(copy, folder, 1)
    assert code == 0
    assert plan["version"] == 1
    assert "sent_version" not in plan
    assert "version_assumed" not in [w["code"] for w in plan["warnings"]]


@pytest.mark.parametrize("kind", ["docx", "pptx"])
def test_copy_without_the_property_is_compared_with_the_latest_version(tmp_path, kind, capsys):
    folder = _built_twice(tmp_path, kind)
    stem = KINDS[kind][0]
    copy = tmp_path / f"{stem}-reviewed.{kind}"
    _rewrite(folder / "v1" / f"{stem}.{kind}", copy, None)
    assert _property(copy) is None
    code, plan = _read(copy, folder, 2)
    assert code == 0
    assert plan["version"] == 2
    warnings = [w for w in plan["warnings"] if w["code"] == "version_assumed"]
    assert len(warnings) == 1
    assert "2" in warnings[0]["message"]


@pytest.mark.parametrize("kind", ["docx", "pptx"])
def test_copy_naming_a_missing_version_is_compared_with_the_latest_version(tmp_path, kind):
    folder = _built_twice(tmp_path, kind)
    stem = KINDS[kind][0]
    copy = tmp_path / f"{stem}-reviewed.{kind}"
    _rewrite(folder / "v1" / f"{stem}.{kind}", copy, "99")
    code, plan = _read(copy, folder, 2)
    assert code == 0
    assert plan["version"] == 2
    warnings = [w for w in plan["warnings"] if w["code"] == "version_assumed"]
    assert len(warnings) == 1
    assert "2" in warnings[0]["message"]
