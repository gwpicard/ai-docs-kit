"""Gathered facts kept beside a working file, separate from rendered layout facts."""

import os
import tempfile
from pathlib import Path

from pydantic import BaseModel, TypeAdapter, ValidationError

from ai_docs_kit.model.text import NonBlank


class GatheredFact(BaseModel):
    text: NonBlank
    source: NonBlank
    locator: NonBlank | None = None


class GatheredFactsError(Exception):
    """A facts file cannot be read or written safely."""


_FACTS = TypeAdapter(list[GatheredFact])


def gathered_facts_path(working: Path) -> Path:
    return working.parent / ".ai_docs_kit" / "facts" / f"{working.name}.json"


def read_gathered_facts(path: Path, *, missing_ok: bool = False) -> list[GatheredFact]:
    try:
        return _FACTS.validate_json(path.read_bytes())
    except FileNotFoundError as error:
        if missing_ok:
            return []
        raise GatheredFactsError(f"{path}: no such facts file") from error
    except (OSError, ValidationError) as error:
        raise GatheredFactsError(
            f"{path}: cannot read facts; expected a JSON list with non-blank text, source and optional locator"
        ) from error


def add_gathered_facts(working: Path, incoming: Path, source_keys: set[str]) -> int:
    facts = read_gathered_facts(incoming)
    for fact in facts:
        if fact.source not in source_keys:
            raise GatheredFactsError(f"{incoming}: unknown source key {fact.source!r}")
    path = gathered_facts_path(working)
    stored = read_gathered_facts(path, missing_ok=True)
    seen = {(fact.text, fact.source, fact.locator) for fact in stored}
    added = 0
    for fact in facts:
        key = (fact.text, fact.source, fact.locator)
        if key not in seen:
            seen.add(key)
            stored.append(fact)
            added += 1
    temporary: str | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".facts-", dir=path.parent)
        with os.fdopen(fd, "wb") as stream:
            stream.write(_FACTS.dump_json(stored, indent=2))
        os.replace(temporary, path)
    except OSError as error:
        raise GatheredFactsError(f"{path}: cannot store facts: {error}") from error
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)
    return added
