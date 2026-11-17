"""Deterministic readiness checks for stored versions."""

from datetime import UTC, datetime

from pydantic import TypeAdapter

from ai_docs_kit.model import Finding
from ai_docs_kit.store import Version, update_manifest


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
    return reasons


def sent_gate(version: Version) -> list[str]:
    look = version.manifest.look
    if look is None or look.agent is None:
        return ["no look entry"]
    errors = sum(f.severity == "error" for f in look.agent)
    return [f"{errors} look errors"] if errors else []


def mark_sent(version: Version, to: str, *, force: bool = False, reason: str | None = None) -> list[str]:
    if force and (reason is None or not reason.strip()):
        raise ValueError("--force requires a non-blank --reason")
    reasons = sent_gate(version)
    if reasons and not force:
        return reasons
    manifest = version.manifest
    changes = {
        "state": "sent",
        "sent_to": [*manifest.sent_to, to],
        "sent_on": [*manifest.sent_on, datetime.now(UTC).strftime("%Y-%m-%d")],
    }
    if reasons:
        changes["forced_reason"] = reason
    update_manifest(version.path, **changes)
    return reasons


def mark_ready(version: Version, *, force: bool = False, reason: str | None = None) -> list[str]:
    if force and (reason is None or not reason.strip()):
        raise ValueError("--force requires a non-blank --reason")
    reasons = ship_gate(version)
    if force:
        update_manifest(version.path, state="ready", forced_reason=reason)
    elif not reasons:
        update_manifest(version.path, state="ready")
    return reasons
