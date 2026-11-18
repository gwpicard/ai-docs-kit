"""Word bookmark names for section ids: always valid in Word, and recoverable from the copy."""

import hashlib
import re

ENCODED = "Xenc_"
HASHED = "Xh_"
MAX_LENGTH = 40
PLAIN_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,39}")


def _encode(section_id: str) -> str:
    body = "".join(c if c.isascii() and c.isalnum() else "__" if c == "_" else f"_x{ord(c):x}_" for c in section_id)
    return ENCODED + body


def hashed_name(section_id: str) -> str:
    return HASHED + hashlib.sha256(section_id.encode("utf-8")).hexdigest()[:16]


def bookmark_name(section_id: str) -> str:
    """A Word-valid bookmark name: the id itself when Word accepts it, else a reversible encoding, else a short hash.

    A hashed name (`Xh_` plus a hash) cannot be reversed; the copy stores the map to the id.
    """
    if PLAIN_NAME.fullmatch(section_id) and not section_id.startswith((ENCODED, HASHED)):
        return section_id
    encoded = _encode(section_id)
    return encoded if len(encoded) <= MAX_LENGTH else hashed_name(section_id)


def is_hashed(name: str) -> bool:
    return name.startswith(HASHED)


def section_of(name: str, stored: dict[str, str] | None = None) -> str:
    """The section id a bookmark name stands for.

    A hashed name is looked up in `stored` and returned as it is when absent; a name not made by
    `bookmark_name` is returned as it is.
    """
    if is_hashed(name):
        return (stored or {}).get(name, name)
    if not name.startswith(ENCODED):
        return name
    return re.sub(
        r"__|_x([0-9a-f]+)_", lambda m: "_" if m.group(1) is None else chr(int(m.group(1), 16)), name[len(ENCODED) :]
    )
