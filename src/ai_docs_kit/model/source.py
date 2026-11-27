from collections.abc import Sequence
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

Format = Literal["slides", "doc"]
ContentField = Annotated[str, Field(pattern=r"^(?:(?:paragraphs|items)\[[0-9]+\]|data)$")]


def content_fields(paragraphs: int, items: int, data: bool, order: Sequence[str] = ()) -> list[str]:
    """Resolve recorded field order, retaining new fields and ignoring removed or repeated ones.

    Older sections have no order and keep the serialiser's items, paragraphs, data fallback.
    """
    fields = [*[f"items[{i}]" for i in range(items)], *[f"paragraphs[{i}]" for i in range(paragraphs)]]
    if data:
        fields.append("data")
    available = set(fields)
    result = []
    for field in [*order, *fields]:
        if field in available:
            result.append(field)
            available.remove(field)
    return result


class Source(BaseModel):
    key: str
    text: str


class Citation(BaseModel):
    key: str
    locator: str | None = None


class Item(BaseModel):
    head: str | None = None
    body: str
    sub: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


class Section(BaseModel):
    id: str | None = None
    intent: str
    section: str | None = None
    component: str | None = None
    because: str | None = None
    owner: Literal["human", "ai"] | None = None
    lock: Literal["text", "all"] | None = None
    page: Literal["new"] | None = None
    span: Literal["column", "full"] | None = None
    redraft: str | None = None
    title: str | None = None
    items: list[Item] = Field(default_factory=list)
    paragraphs: list[str] = Field(default_factory=list)
    content_order: list[ContentField] = Field(default_factory=list)
    code: list[str] = Field(default_factory=list)
    note: str | None = None
    spoken: str | None = None
    source_line: str | None = None
    data: dict[str, Any] | None = None
    image: str | None = None
    icons: list[str] = Field(default_factory=list)
    extra_attrs: dict[str, str] = Field(default_factory=dict)

    def ordered_content(self) -> list[str]:
        """Return paragraph, item and data field paths in working-file order."""
        return content_fields(len(self.paragraphs), len(self.items), self.data is not None, self.content_order)


class Document(BaseModel):
    front: dict[str, Any]
    format: Format
    context: str = ""
    sources: list[Source] = Field(default_factory=list)
    sections: list[Section]
    rev: int = 0
