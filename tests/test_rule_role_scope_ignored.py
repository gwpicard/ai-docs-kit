"""A font-family rule examines only the roles named in its scope."""

import json
import shutil

import pytest
import yaml

from ai_docs_kit.cli import main
from ai_docs_kit.theme import NEUTRAL_ROOT


@pytest.mark.parametrize(("role", "family"), [("heading", "Source Serif 4"), ("paragraph", "Inter")])
def test_font_family_scope_excludes_other_rendered_roles(tmp_path, role, family):
    theme = tmp_path / "theme"
    shutil.copytree(NEUTRAL_ROOT, theme, ignore=shutil.ignore_patterns("exemplars"))
    authored = theme / "rules" / "authored"
    authored.mkdir(parents=True)
    rule = {
        "id": "manual.role-font",
        "title": "Use the font for this role",
        "origin": "manual",
        "strength": "hard",
        "status": "active",
        "severity": "error",
        "tier": "geometry",
        "scope": {"format": "doc"},
        "check": {"kind": "font-family", "allowed": ["Source Serif 4", "Inter"]},
        "remedy": {"class": "engine", "hint": "Use the font assigned to the role."},
        "provenance": {"by": "Dana"},
    }
    path = authored / "role-font.yaml"
    path.write_text(yaml.safe_dump(rule), encoding="utf-8")
    source = tmp_path / "note.md"
    source.write_text(
        "---\ndoctype: report\nformat: doc\ntitle: Note\n---\n\n"
        '::: {#timing .section intent="body"}\n## Timing\n\nThe plan names a date.\n:::\n',
        encoding="utf-8",
    )
    assert main(["check", str(source), "--theme", str(theme), "--out", str(tmp_path / "control")]) == 0
    rule["scope"]["roles"] = [role]
    rule["check"]["allowed"] = [family]
    path.write_text(yaml.safe_dump(rule), encoding="utf-8")
    out = tmp_path / "scoped"

    code = main(["check", str(source), "--theme", str(theme), "--out", str(out)])
    findings = json.loads((out / "note.findings.json").read_text(encoding="utf-8"))

    assert code == 0, f"The {role} rule reported text from another role: {findings}"
    assert not [finding for finding in findings if finding["rule_id"] == rule["id"]]

    rule["check"]["allowed"] = ["Inter" if role == "heading" else "Source Serif 4"]
    path.write_text(yaml.safe_dump(rule), encoding="utf-8")
    defective = tmp_path / "wrong-role-font"
    assert main(["check", str(source), "--theme", str(theme), "--out", str(defective)]) == 1
    defects = json.loads((defective / "note.findings.json").read_text(encoding="utf-8"))
    assert any(finding["rule_id"] == rule["id"] for finding in defects)
