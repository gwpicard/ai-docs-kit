from pydantic import BaseModel

from ai_docs_kit.model.source import Format
from ai_docs_kit.model.text import NonBlank
from ai_docs_kit.theme.loader import _read_model
from ai_docs_kit.theme.models import Theme

VOICE_FILE = "voice/terminology.yaml"


class Term(BaseModel):
    preferred: NonBlank
    avoid: list[NonBlank]


class Voice(BaseModel):
    summary: dict[Format, NonBlank] = {}
    banned: list[NonBlank] = []
    terminology: list[Term] = []


def load_voice(theme: Theme) -> Voice:
    """Read the theme's voice/terminology.yaml, or give an empty Voice when the file is absent."""
    path = theme.root / VOICE_FILE
    if not path.is_file():
        return Voice()
    return _read_model(path, Voice)
