"""The review plan: what a reviewer changed, keyed by section, and what needs the owner's confirmation."""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CommentItem(_Model):
    kind: Literal["comment"] = "comment"
    author: str | None = Field(description="The commenter; null when the file does not name them.")
    id: str | None = Field(default=None, description="The comment's id in the file, for a modern deck comment.")
    reply_to: str | None = Field(default=None, description="The id of the comment this one replies to, if a reply.")
    text: str
    anchor: str = Field(description="The words the comment is attached to.")
    accepted: bool | None = Field(
        default=None, description="The person's decision; set by the person, not by `review read`."
    )
    action: Literal["apply", "redraft", "skip"] | None = Field(default=None, description="What accepting does.")
    proposal: str | None = Field(default=None, description="The new wording of the section, for apply.")
    ask: str | None = Field(default=None, description="The redraft ask to write on the section, for redraft.")
    spans: list[str] = Field(
        default_factory=list,
        description="The ids of every section the comment's range overlaps, in document order; each copy carries all.",
    )
    slide: int | None = Field(default=None, description="The slide number (1-based, sent order), for a deck comment.")
    shape: str | None = Field(default=None, description="The shape name the comment is attached to, if any.")


class Emphasis(_Model):
    kind: Literal["bold", "italic", "colour"]
    text: str
    value: str | None = Field(default=None, description="The colour as hex, for a colour hint.")


class SectionPlan(_Model):
    wording: str | None = Field(description="The applied wording of the section, null when it is unchanged.")
    owner: Literal["human"] | None = Field(description="human when a reviewer wrote the wording.")
    items: list[str] | None = Field(
        default=None, description="The section's list items from the Word copy, in order; null when unchanged."
    )
    fields: dict[str, str] = Field(
        default_factory=dict, description="The applied text of each changed field, by field path (decks)."
    )
    confirm: list[CommentItem] = Field(default_factory=list)
    emphasis: list[Emphasis] = Field(default_factory=list)


class StructureItem(_Model):
    kind: Literal["delete", "reorder", "unplaced"]
    text: str
    section: str | None = Field(default=None, description="The deleted section, for a delete item.")
    after: str | None = Field(default=None, description="The section an unplaced text follows, if any.")
    author: str | None = None
    order: list[str] | None = Field(default=None, description="The new section order, for a reorder item.")
    accepted: bool | None = Field(
        default=None, description="The person's decision; set by the person, not by `review read`."
    )
    action: Literal["restructure"] | None = Field(default=None, description="Set when the item can be applied.")


class Warning(_Model):
    code: str
    message: str


class ReviewPlan(_Model):
    version: int = Field(description="The version the copy was compared with.")
    review_copy: str = Field(description="The file name of the review copy.")
    sections: dict[str, SectionPlan]
    confirm: list[StructureItem] = Field(default_factory=list)
    warnings: list[Warning] = Field(default_factory=list)


def export_review_schema(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "ReviewPlan.schema.json"
    path.write_text(
        json.dumps(ReviewPlan.model_json_schema(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path
