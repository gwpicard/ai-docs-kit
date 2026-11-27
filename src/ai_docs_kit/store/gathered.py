"""Gathered facts kept beside a working file, separate from rendered layout facts."""

import os
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, TypeAdapter, ValidationError

from ai_docs_kit.loop.guards import NUMBER, _calculation, support_tokens
from ai_docs_kit.model.text import NonBlank
from ai_docs_kit.sources import source_text_at


class GatheredFact(BaseModel):
    text: NonBlank
    source: NonBlank
    locator: NonBlank | None = None
    verification: Literal["verified", "unverified"] = "verified"


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


def _numbers(text: str) -> set[str]:
    return {token for token in support_tokens(text) if NUMBER.fullmatch(token)}


def _validate_facts(
    working: Path, incoming: Path, facts: list[GatheredFact], stored: list[GatheredFact], sources: dict[str, str]
) -> list[str]:
    allowed = set().union(*(_numbers(fact.text) for fact in stored))
    errors = []
    warnings = []
    texts: dict[tuple[str, str | None], str] = {}
    for fact in facts:
        citation = fact.source + (f" {fact.locator}" if fact.locator else "")
        prefix = " ".join(f"{incoming}: [{citation}] {fact.text}".split())
        if fact.source not in sources:
            errors.append(f"{prefix}: unknown source key {fact.source!r}")
            continue
        source = sources[fact.source].partition(", ")[0].strip()
        unverified = source.lower().startswith(("https://", "http://"))
        text = ""
        if not unverified:
            try:
                key = (fact.source, fact.locator)
                if key not in texts:
                    texts[key] = source_text_at(working.parent / source, fact.locator)
                text = texts[key]
            except Exception as error:
                reason = " ".join(str(error).split())
                errors.append(f"{prefix}: cannot read source {source!r}: {reason}")
                continue
        if fact.text.lstrip().startswith("calc:"):
            if _calculation(fact.text, allowed) is None:
                errors.append(f"{prefix}: calculation has an incorrect result or operands from no earlier fact")
                continue
        elif not unverified and (missing := _numbers(fact.text) - _numbers(text)):
            errors.append(f"{prefix}: figures absent from source {source!r}: {', '.join(sorted(missing))}")
            continue
        fact.verification = "unverified" if unverified else "verified"
        if unverified:
            warnings.append(f"warning: [{citation}] unverified fact from URL source {source}")
        allowed.update(_numbers(fact.text))
    if errors:
        raise GatheredFactsError("\n".join(errors))
    return warnings


def add_gathered_facts(working: Path, incoming: Path, sources: dict[str, str]) -> tuple[int, list[str]]:
    """Validate and atomically add a batch, returning its count and URL warnings."""
    facts = read_gathered_facts(incoming)
    path = gathered_facts_path(working)
    stored = read_gathered_facts(path, missing_ok=True)
    warnings = _validate_facts(working, incoming, facts, stored, sources)
    seen = {(fact.text, fact.source, fact.locator): fact for fact in stored}
    added = 0
    for fact in facts:
        key = (fact.text, fact.source, fact.locator)
        if key not in seen:
            seen[key] = fact
            stored.append(fact)
            added += 1
        else:
            seen[key].verification = fact.verification
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
    return added, warnings
