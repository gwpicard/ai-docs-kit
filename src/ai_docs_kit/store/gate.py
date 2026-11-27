"""Deterministic readiness checks for stored versions."""

from pydantic import TypeAdapter

from ai_docs_kit.model import Finding
from ai_docs_kit.store import Version


def ship_gate(version: Version) -> list[str]:
    manifest = version.manifest
    reasons: list[str] = []
    if manifest.look is None:
        reasons.append("not fully looked at")
    elif manifest.look.could_not:
        reasons.append(f"not fully looked at: {'; '.join(manifest.look.could_not)}")
    if manifest.findings.error:
        reasons.append(f"{manifest.findings.error} error findings")
    if manifest.final and manifest.gaps:
        reasons.append(f"{len(manifest.gaps)} gaps")
    findings = TypeAdapter(list[Finding]).validate_json((version.path / "findings.json").read_bytes())
    if any(f.tier == "semantic" and f.severity == "error" and f.corroborated is not True for f in findings):
        reasons.append("unacknowledged vision findings")
    if manifest.look is not None and manifest.look.agent is None:
        reasons.append("not looked at by the look agent")
    return reasons
