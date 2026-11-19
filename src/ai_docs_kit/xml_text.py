"""One sanitiser for text that goes into an Office copy, shared by the Word and PowerPoint writers."""

import re

_ILLEGAL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")


def strip_xml_illegal(text: str) -> str:
    """Drop the characters XML 1.0 cannot carry (control characters, lone surrogates, U+FFFE and U+FFFF)."""
    return _ILLEGAL.sub("", text)
