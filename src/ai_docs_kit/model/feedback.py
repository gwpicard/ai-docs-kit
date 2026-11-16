"""A person's comment on a report."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

DEFAULT_PERSON = "local"

FeedbackState = Literal["open", "resolved"]


class Feedback(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    doc: str
    person: str
    parent: str | None = None
    section_id: str | None = None
    field: str | None = None
    version: int | None = None
    text: str
    state: FeedbackState = "open"
    created: str
    resolved: str | None = None
    resolved_by: str | None = None
