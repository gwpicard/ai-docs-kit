from datetime import date
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_docs_kit.model.source import Format
from ai_docs_kit.model.text import NonBlank

Tier = Literal["source", "geometry", "pixel", "semantic"]
ValueLabel = Literal["measured", "derived", "inferred", "answered"]
Severity = Literal["error", "warning", "info"]


class Box(BaseModel):
    """A region on a page, in points."""

    x: float
    y: float
    w: float
    h: float


class Remedy(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    class_: Literal["redraft", "restructure", "tune", "engine", "report", "ask"] = Field(alias="class")
    hint: NonBlank


class Provenance(BaseModel):
    label: ValueLabel | None = None
    source: dict[str, Any] | None = None
    created: date | None = None
    by: NonBlank | None = None


class Scope(BaseModel):
    format: Format | None = None
    roles: list[NonBlank] | None = None
    components: list[NonBlank] | None = None
    intents: list[NonBlank] | None = None


class Rule(BaseModel):
    id: NonBlank
    title: NonBlank
    origin: Literal["ingested", "manual", "feedback", "measured"]
    strength: Literal["hard", "soft"]
    status: Literal["proposed", "probation", "active", "retired"] = "proposed"
    severity: Severity
    tier: Tier
    loop: Literal["micro", "macro", "both"] = "both"
    scope: Scope = Field(default_factory=Scope)
    check: dict[str, Any]
    remedy: Remedy
    provenance: Provenance
    stats: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _measured_is_never_hard(self) -> Self:
        if self.strength == "hard" and self.origin == "measured":
            raise ValueError("a measurement alone never creates a hard rule")
        return self


class Finding(BaseModel):
    id: str
    rule_id: str
    tier: Tier
    severity: Severity
    format: Format
    section_id: str | None = None
    owner: str | None = None
    role: str | None = None
    page: int | None = None
    region: Box | None = None
    message: str
    measured: dict[str, Any] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)
    fingerprint: str
    remedy: Remedy
    corroborated: bool | None = None
    confidence: float | None = None
