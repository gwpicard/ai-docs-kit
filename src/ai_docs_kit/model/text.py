from typing import Annotated

from pydantic import AfterValidator, StringConstraints


def _refuse_whitespace(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


NonBlank = Annotated[str, StringConstraints(min_length=1), AfterValidator(_refuse_whitespace)]
"""A string a person or agent writes: refused when empty or only whitespace."""
