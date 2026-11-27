from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, get_args

from ai_docs_kit.facts.layout import LayoutFacts
from ai_docs_kit.model import Box, Document, Finding, Rule, Section
from ai_docs_kit.model.rules import Severity, Tier
from ai_docs_kit.render.compose import Composition
from ai_docs_kit.theme import Theme

if TYPE_CHECKING:
    from ai_docs_kit.agents.gatherer import Fact

# Tiers run in the order the model declares them.
TIERS: tuple[Tier, ...] = get_args(Tier)
GRID = 8


@dataclass
class CheckContext:
    doc: Document
    facts: LayoutFacts | None = None
    tokens: dict[str, str] = field(default_factory=dict)
    theme: Theme | None = None
    composition: Composition | None = None
    final: bool = False
    assets: list[Path] | None = None
    pages_png: list[Path] = field(default_factory=list)

    source_facts: Sequence[Fact] | None = None
    word_copy: Path | None = None

    def page_png(self, n: int) -> Path:
        if n < 1 or n > len(self.pages_png):
            raise IndexError(f"no image for page {n}")
        return self.pages_png[n - 1]


class Check(Protocol):
    tier: Tier | None

    def run(self, ctx: CheckContext, rule: Rule) -> list[Finding]: ...


CHECKS: dict[str, Check] = {}


class UnknownCheckError(KeyError):
    pass


def register(kind: str) -> Callable[[type], type]:
    def decorate(cls: type) -> type:
        if kind in CHECKS:
            raise ValueError(f"check kind {kind!r} is already registered")
        CHECKS[kind] = cls()
        return cls

    return decorate


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()


def _cell(region: Box | None, page_size: tuple[float, float] | None) -> str:
    if region is None or page_size is None:
        return "-"
    width, height = page_size
    col = int((region.x + region.w / 2) / width * GRID)
    row = int((region.y + region.h / 2) / height * GRID)
    return f"{min(max(col, 0), GRID - 1)},{min(max(row, 0), GRID - 1)}"


def fingerprint(
    rule_id: str,
    section_id: str | None,
    role: str | None,
    region: Box | None,
    page_size: tuple[float, float] | None,
    key: str | None = None,
) -> str:
    value = f"{rule_id}|{section_id}|{role}|{_cell(region, page_size)}"
    if key is not None:
        value += f"|{key}"
    return _sha1(value)


def _page_size(ctx: CheckContext, page: int | None) -> tuple[float, float] | None:
    if ctx.facts is None or not ctx.facts.pages:
        return None
    pages = ctx.facts.pages
    chosen = next((p for p in pages if p.page == page), pages[0])
    return (chosen.width, chosen.height)


def section_key(section: Section, index: int) -> str:
    """The id of a section, or `section-<index>` when it has none."""
    return section.id if section.id is not None else f"section-{index}"


class FindingKey(str):
    """A finding `key` that remembers the section key of the section it is about."""

    owner: str | None

    def __new__(cls, text: str, owner: str | None) -> FindingKey:
        key = super().__new__(cls, text)
        key.owner = owner
        return key


def finding_key(section: Section, index: int, detail: str | None = None) -> FindingKey | None:
    """The `key` for a finding about one section; `detail` tells apart several findings in it.

    A section with an id is already told apart by `section_id`, so it keeps `detail` alone.
    """
    owner = section_key(section, index)
    if section.id is not None:
        return None if detail is None else FindingKey(detail, owner)
    return FindingKey(owner if detail is None else f"{owner}:{detail}", owner)


def make_finding(
    rule: Rule,
    ctx: CheckContext,
    *,
    message: str,
    section_id: str | None = None,
    role: str | None = None,
    page: int | None = None,
    region: Box | None = None,
    measured: dict[str, Any] | None = None,
    severity: Severity | None = None,
    key: str | None = None,
    owner: str | None = None,
) -> Finding:
    if owner is None:
        owner = key.owner if isinstance(key, FindingKey) else section_id
    fp = fingerprint(rule.id, section_id, role, region, _page_size(ctx, page), key=key)
    finding = Finding(
        id=_sha1(f"{rule.id}|{section_id}|{fp}")[:12],
        rule_id=rule.id,
        tier=rule.tier,
        severity=severity if severity is not None else rule.severity,
        format=ctx.doc.format,
        section_id=section_id,
        owner=owner,
        role=role,
        page=page,
        region=region,
        message=message,
        measured=measured or {},
        fingerprint=fp,
        remedy=rule.remedy,
    )
    return finding


def _applies(rule: Rule, ctx: CheckContext) -> bool:
    if rule.status not in ("active", "probation"):
        return False
    return rule.scope.format is None or rule.scope.format == ctx.doc.format


def _check_for(rule: Rule) -> Check:
    kind = rule.check["kind"]
    if kind not in CHECKS:
        raise UnknownCheckError(f"no check registered for kind {kind!r}")
    return CHECKS[kind]


def _tiers_to_run(ctx: CheckContext) -> tuple[Tier, ...]:
    if ctx.facts is None:
        return ("source",)
    return tuple(tier for tier in TIERS if tier != "pixel" or ctx.pages_png)


def _in_scope(finding: Finding, rule: Rule, ctx: CheckContext) -> bool:
    scope = rule.scope
    if scope.components is not None and (
        ctx.composition is None
        or not any(
            section_key(s, i) == finding.owner and composed.component in scope.components
            for i, (s, composed) in enumerate(zip(ctx.doc.sections, ctx.composition.sections, strict=False))
        )
    ):
        return False
    if scope.intents is not None and not any(
        section_key(s, i) == finding.owner and s.intent in scope.intents for i, s in enumerate(ctx.doc.sections)
    ):
        return False
    return True


def _on_probation(rule: Rule, findings: list[Finding]) -> list[Finding]:
    """A probation rule only warns, so it never blocks a build."""
    if rule.status != "probation":
        return findings
    return [f.model_copy(update={"severity": "warning"}) if f.severity == "error" else f for f in findings]


def run_checks(rules: list[Rule], ctx: CheckContext) -> list[Finding]:
    applicable = [(rule, _check_for(rule)) for rule in rules if _applies(rule, ctx)]
    blocked: set[str] = set()
    findings: list[Finding] = []
    for tier in _tiers_to_run(ctx):
        produced = [
            f
            for rule, check in applicable
            if (check.tier or rule.tier) == tier
            for f in _on_probation(rule, check.run(ctx, rule))
            if _in_scope(f, rule, ctx)
        ]
        # Block by owning section, so id-less sections do not share the key None; document-level findings block nothing.
        kept = [f for f in produced if f.owner is None or f.owner not in blocked]
        blocked |= {f.owner for f in kept if f.severity == "error" and f.owner is not None}
        findings.extend(kept)
    return _unique(findings)


def _unique(findings: list[Finding]) -> list[Finding]:
    seen: set[str] = set()
    unique: list[Finding] = []
    for finding in findings:
        if finding.fingerprint not in seen:
            seen.add(finding.fingerprint)
            unique.append(finding)
    return unique
