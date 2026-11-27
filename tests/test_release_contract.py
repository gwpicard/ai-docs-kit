"""Judge the first release and the version agreement required for later releases."""

import ast
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILES = ("pyproject.toml", ".claude-plugin/plugin.json", "src/ai_docs_kit/__init__.py", "CHANGELOG.md")
RELEASE_HEADING = re.compile(r"^##\s+\[?v?(\d+\.\d+\.\d+)\]?(?:\s.*)?$", re.MULTILINE)


def _read(root: Path, name: str) -> str:
    path = root / name
    assert path.is_file(), f"release contract needs {name}"
    return path.read_text(encoding="utf-8")


def _versions(root: Path) -> dict[str, str]:
    project = tomllib.loads(_read(root, VERSION_FILES[0]))["project"]["version"]
    plugin = json.loads(_read(root, VERSION_FILES[1]))["version"]
    assignments = ast.parse(_read(root, VERSION_FILES[2])).body
    package = [
        ast.literal_eval(node.value)
        for node in assignments
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets)
    ]
    assert len(package) == 1, "__init__.py must declare one __version__"
    heading = RELEASE_HEADING.search(_read(root, VERSION_FILES[3]))
    assert heading is not None, "CHANGELOG.md needs a versioned release heading"
    return dict(zip(VERSION_FILES, (project, plugin, package[0], heading[1]), strict=True))


def _assert_versions_agree(root: Path) -> None:
    versions = _versions(root)
    assert len(set(versions.values())) == 1, f"release versions disagree: {versions}"


def test_first_release_metadata_is_0_1_0():
    project = tomllib.loads(_read(ROOT, VERSION_FILES[0]))["project"]["version"]
    plugin = json.loads(_read(ROOT, VERSION_FILES[1]))["version"]
    from ai_docs_kit import __version__

    assert (project, plugin, __version__) == ("0.1.0",) * 3


def test_installed_version_command_prints_the_first_release():
    command = Path(sys.executable).parent / "ai-docs-kit"
    result = subprocess.run([str(command), "--version"], capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "ai_docs_kit 0.1.0\n"
    assert result.stderr == ""


def test_initial_changelog_entry_records_the_current_surfaces():
    changelog = _read(ROOT, "CHANGELOG.md")
    releases = list(RELEASE_HEADING.finditer(changelog))
    initial = next((match for match in releases if match[1] == "0.1.0"), None)
    assert initial is not None, "record the initial 0.1.0 release"
    # Inspect this entry only: a template or another release cannot supply its surfaces.
    following = re.search(r"^##\s", changelog[initial.end() :], re.MULTILINE)
    end = initial.end() + following.start() if following else len(changelog)
    entry = changelog[initial.end() : end].lower()
    for command in ("build", "look", "review read", "review apply", "rule test", "brand", "doctor"):
        assert re.search(rf"\b{re.escape(command)}\b", entry), f"0.1.0 must describe the {command} command"
    for surface, patterns in {
        "command results": (r"exit", r"output"),
        "working-file format": (r"working[ -]file", r"markdown|\.md", r"front[ -]matter", r"section", r"\bid\b|ids"),
        "version format": (
            r"\.versions",
            r"vN|v<n>|v\d",
            r"manifest\.json",
            r"composition\.json",
            r"layout\.json",
            r"pages/",
        ),
        "review readers": (r"word", r"powerpoint", r"malformed|hostile|archive"),
        "editable copies": (r"\.pptx", r"\.docx", r"bookmark", r"field", r"section"),
        "rulebook and checks": (r"rulebook", r"check", r"seeded[ -]defect"),
        "renderer": (r"typst", r"composition", r"layout facts", r"golden"),
        "skills and agents": (r"skill", r"agent", r"\bcreate\b", r"\breview\b"),
    }.items():
        for pattern in patterns:
            assert re.search(pattern, entry, re.IGNORECASE), f"0.1.0 must describe {surface}: {pattern}"
    assert "Breaking:" in changelog, "the format for later entries must mark breaking changes as Breaking:"


def test_contributing_describes_the_release_round_trip():
    contributing = _read(ROOT, "CONTRIBUTING.md")
    heading = re.search(r"^(#{2,6})\s+[^\n]*releas[^\n]*$", contributing, re.MULTILINE | re.IGNORECASE)
    assert heading is not None, "CONTRIBUTING.md needs release instructions"
    after = contributing[heading.end() :]
    following = re.search(rf"^#{{1,{len(heading[1])}}}\s", after, re.MULTILINE)
    release = after[: following.start()] if following else after
    for name in ("pyproject.toml", ".claude-plugin/plugin.json", "__version__", "__init__.py", "CHANGELOG.md"):
        assert name in release, f"release instructions must name {name}"
    for description, pattern in {
        "update the versions": r"updat\w*[\s\S]*version",
        "add the changelog entry": r"(?:add|write|record)\w*[\s\S]*(?:changelog|entry)",
        "open a pull request": r"(?:open|creat|submit)\w*[\s\S]*pull request",
        "tag after the merge": r"merg\w*[\s\S]*git\s+tag\b[^\n]*vX\.Y\.Z",
        "tag on main": r"\bmain\b",
        "publish release notes": r"(?:publish|creat)\w*[\s\S]*(?:GitHub release|release notes)",
        "take notes from the changelog entry": r"(?:changelog[\s\S]*(?:notes|entry)|notes[\s\S]*changelog)",
    }.items():
        assert re.search(pattern, release, re.IGNORECASE), f"release instructions must explain how to {description}"


def _seed_release(root: Path, versions: list[str], *, rearranged: bool, older_version: str = "0.0.1") -> None:
    project, plugin, package, changelog = versions
    (root / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (root / "src/ai_docs_kit").mkdir(parents=True, exist_ok=True)
    metadata = f'name = "synthetic-kit"\nversion = "{project}"\n'
    if rearranged:
        metadata = f'version = "{project}"\nname = "synthetic-kit"\n'
    (root / VERSION_FILES[0]).write_text(f"[project]\n{metadata}", encoding="utf-8")
    manifest = (
        {"name": "synthetic-kit", "version": plugin} if rearranged else {"version": plugin, "name": "synthetic-kit"}
    )
    (root / VERSION_FILES[1]).write_text(json.dumps(manifest), encoding="utf-8")
    (root / VERSION_FILES[2]).write_text(f'"""Synthetic package."""\n__version__ = "{package}"\n', encoding="utf-8")
    heading = f"## [{changelog}] - 2026-11-27" if rearranged else f"## {changelog}"
    prefix = "# Changelog\n\n## Unreleased\n\n" if rearranged else "# Changelog\n\n"
    (root / VERSION_FILES[3]).write_text(
        f"{prefix}{heading}\n\nInitial surfaces.\n\n## {older_version}\n\nOlder entry.\n", encoding="utf-8"
    )


def test_release_versions_agree_and_seeded_mismatches_are_rejected(tmp_path):
    # Pair matching releases with a defect in each source, including the top heading.
    # A historical matching heading must never conceal a mismatched newest release.
    for rearranged, version in ((False, "0.1.0"), (True, "0.2.0")):
        matching = [version] * 4
        _seed_release(tmp_path, matching, rearranged=rearranged)
        _assert_versions_agree(tmp_path)
        for index in range(len(VERSION_FILES)):
            mismatched = matching.copy()
            mismatched[index] = "0.3.0"
            older_version = version if index == 3 else "0.0.1"
            _seed_release(tmp_path, mismatched, rearranged=rearranged, older_version=older_version)
            with pytest.raises(AssertionError, match="release versions disagree"):
                _assert_versions_agree(tmp_path)
    _assert_versions_agree(ROOT)
