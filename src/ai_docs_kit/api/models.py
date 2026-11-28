"""Stable result models for the public Python and command-line JSON surfaces.

New fields must have defaults so saved results from earlier releases still load.
"""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ai_docs_kit.model import Finding, Section
from ai_docs_kit.store import Version


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EditResult(_Model):
    rev: int
    section: Section


class HistoryResult(_Model):
    rev: int
    target_rev: int


class EditError(_Model):
    code: str
    message: str


class BuildResult(_Model):
    version: Path
    outputs: list[Path]
    findings: list[Finding]

    @classmethod
    def from_version(cls, version: Version, findings: list[Finding]) -> "BuildResult":
        """Point at the immutable copies, rather than the next build's outputs."""
        return cls(
            version=version.path,
            outputs=[(version.path / name).absolute() for name in version.manifest.outputs],
            findings=findings,
        )


class PageRegion(_Model):
    section: str
    role: str
    x: float
    y: float
    w: float
    h: float
    field: str | None = None


class Page(_Model):
    page: int
    image: str
    width: float
    height: float
    sections: list[str]
    regions: list[PageRegion] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)


class FieldBox(_Model):
    section: str
    field: str
    role: str
    x: float
    y: float
    w: float
    h: float


class FieldPage(_Model):
    page: int
    fields: list[FieldBox]


class PreviewResult(_Model):
    pngs: list[Path]
    pages: list[Page]
    fields: list[FieldPage]
    findings: list[Finding]
