import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from ai_docs_kit.model import Section
from ai_docs_kit.render.typst import run_typst

FIELD_PATTERN: re.Pattern[str] = re.compile(
    r"(?:title|note|spoken|source_line|image|paragraphs\[\d+\]|"
    r"items\[\d+\](?:\.(?:head|body|sub\[\d+\]))?|"
    r"data(?:\.[a-z_]+(?:\[\d+\])*)+)"
)


class FieldError(ValueError):
    pass


def field_value(section: Section, field: str) -> Any:
    if not FIELD_PATTERN.fullmatch(field):
        raise FieldError(f"Invalid field: {field}")
    value: Any = section
    try:
        for name, index in re.findall(r"([a-z_]+)|\[(\d+)\]", field):
            if index:
                if not isinstance(value, list):
                    raise FieldError(f"Field is not a list: {field}")
                value = value[int(index)]
            elif isinstance(value, dict):
                value = value[name]
            else:
                value = getattr(value, name)
    except (AttributeError, KeyError, IndexError, TypeError) as error:
        raise FieldError(f"Field not found: {field}") from error
    return value


MARK_QUERY = "query(<ai_docs_kit-mark>).map(it => it.value)"


class SectionMark(BaseModel):
    kind: Literal["section"]
    id: str
    edge: Literal["start", "end"]
    page: int
    x: float
    y: float


class ElementMark(BaseModel):
    kind: Literal["element"]
    role: str
    id: str
    page: int
    x: float
    y: float
    w: float
    h: float
    field: str | None = None


class FitMark(BaseModel):
    kind: Literal["fit"]
    role: str
    id: str
    need: float
    have: float
    ok: bool


Mark = Annotated[SectionMark | ElementMark | FitMark, Field(discriminator="kind")]

_MARK_ADAPTER: TypeAdapter[Mark] = TypeAdapter(Mark)


class MarkError(ValueError):
    pass


def _validate_mark(index: int, raw: Any) -> Mark:
    try:
        return _MARK_ADAPTER.validate_python(raw)
    except ValidationError as error:
        raise MarkError(f"mark {index} is not valid: {error}") from error


def read_marks(main: Path, root: Path, font_paths: Sequence[Path] = ()) -> list[Mark]:
    output = run_typst(["eval", MARK_QUERY, "--in", str(main)], root, font_paths)
    return [_validate_mark(index, raw) for index, raw in enumerate(json.loads(output))]
