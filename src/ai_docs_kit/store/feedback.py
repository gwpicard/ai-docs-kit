"""Comments on a report, kept beside the working file."""

import json
import os
import tempfile
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from ai_docs_kit.model import DEFAULT_PERSON, Feedback, FeedbackState
from ai_docs_kit.render.marks import FIELD_PATTERN
from ai_docs_kit.source import parse

_LOCK = threading.Lock()


class FeedbackError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def feedback_path(doc_path: Path) -> Path:
    return doc_path.with_name(f"{doc_path.stem}.feedback.json")


def load_feedback(doc_path: Path) -> list[Feedback]:
    path = feedback_path(doc_path)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Feedback.model_validate(item) for item in data["feedback"]]


def _save(doc_path: Path, comments: list[Feedback]) -> None:
    path = feedback_path(doc_path)
    text = json.dumps({"feedback": [c.model_dump(mode="json") for c in comments]}, indent=2, ensure_ascii=False)
    handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as temp:
            temp.write(text)
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def _stamp(now: Callable[[], datetime] | None) -> str:
    return (now() if now else datetime.now(UTC)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def add_feedback(
    doc_path: Path,
    text: str,
    *,
    person: str = DEFAULT_PERSON,
    section_id: str | None = None,
    field: str | None = None,
    parent: str | None = None,
    version: int | None = None,
    now: Callable[[], datetime] | None = None,
) -> Feedback:
    text = text.strip()
    if not text:
        raise FeedbackError("empty-text", "A comment needs text")
    if section_id is not None:
        document, _ = parse(doc_path.read_text(encoding="utf-8"))
        if section_id not in {s.id for s in document.sections}:
            raise FeedbackError("unknown-section", f"Unknown section: {section_id}")
    if field is not None:
        if section_id is None:
            raise FeedbackError("field-without-section", "A field needs a section")
        if not FIELD_PATTERN.fullmatch(field):
            raise FeedbackError("bad-field", f"Invalid field: {field}")
    with _LOCK:
        comments = load_feedback(doc_path)
        if parent is not None:
            first = next((c for c in comments if c.id == parent), None)
            if first is None:
                raise FeedbackError("unknown-parent", f"Unknown comment: {parent}")
            if first.parent is not None:
                raise FeedbackError("reply-to-reply", "A reply cannot be answered; reply to the thread's first comment")
            section_id, field = first.section_id, first.field
        comment = Feedback(
            id="fb-" + uuid.uuid4().hex[:12],
            doc=doc_path.stem,
            person=person,
            parent=parent,
            section_id=section_id,
            field=field,
            version=version,
            text=text,
            created=_stamp(now),
        )
        _save(doc_path, [*comments, comment])
    return comment


def set_feedback_state(
    doc_path: Path,
    feedback_id: str,
    state: FeedbackState,
    *,
    person: str = DEFAULT_PERSON,
    now: Callable[[], datetime] | None = None,
) -> Feedback:
    with _LOCK:
        comments = load_feedback(doc_path)
        index = next((i for i, c in enumerate(comments) if c.id == feedback_id), None)
        if index is None:
            raise FeedbackError("unknown-comment", f"Unknown comment: {feedback_id}")
        if comments[index].parent is not None:
            raise FeedbackError("not-a-thread", "Only a thread's first comment has a state")
        resolved = state == "resolved"
        comments[index] = comments[index].model_copy(
            update={
                "state": state,
                "resolved": _stamp(now) if resolved else None,
                "resolved_by": person if resolved else None,
            }
        )
        _save(doc_path, comments)
        return comments[index]
