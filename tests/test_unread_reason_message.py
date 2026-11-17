import zipfile
from pathlib import Path

import pytest

from ai_docs_kit.brand.intake import take_in
from ai_docs_kit.brand.templates import read_templates

TYPES = (
    '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="xml" ContentType="application/xml"/></Types>'
)
BAD_ARCHIVES = {
    "no-content-types": {"notes.txt": "x", "docProps/app.xml": "<Properties/>"},
    "malformed-rels": {"[Content_Types].xml": TYPES, "_rels/.rels": "<Relationships", "docProps/app.xml": "<P/>"},
    "no-main-part": {"[Content_Types].xml": TYPES, "_rels/.rels": "<Relationships/>"},
}
RAW = ("KeyError", "no member", "no item named", "XMLSyntaxError", "Traceback", "line 1, column", "<string>")


@pytest.mark.parametrize("kind", BAD_ARCHIVES)
@pytest.mark.parametrize("name", ["deck.pptx", "report.docx"])
def test_unread_reason_is_a_plain_one_line_message(tmp_path: Path, name: str, kind: str) -> None:
    brand = tmp_path / "acme"
    (brand / "materials" / "templates").mkdir(parents=True)
    with zipfile.ZipFile(brand / "materials" / "templates" / name, "w") as archive:
        for member, text in BAD_ARCHIVES[kind].items():
            archive.writestr(member, text)
    take_in(brand)
    report = read_templates(brand)
    reasons = [u.reason for u in report.unread]
    manifest_reasons = [e.unread for e in take_in(brand).files if e.unread]
    assert reasons or manifest_reasons
    for reason in reasons + manifest_reasons:
        assert "\n" not in reason
        assert not any(token in reason for token in RAW), reason
        assert name in reason or "Office" in reason or "not a" in reason.lower(), reason
