"""The version stamp holds ASCII digits only; any other digit falls back to the latest version."""

import pytest
from tests.test_review_copy_version import _built_twice, _read, _rewrite

from ai_docs_kit.store.stamp import read_version_property

ARABIC_INDIC = "١٢"  # "١٢"
ARABIC_INDIC_TWO = "٢"  # "٢"
SUPERSCRIPT_TWO = "²"  # "²", str.isdigit() is true but int() refuses it


@pytest.mark.parametrize("value", [ARABIC_INDIC, ARABIC_INDIC_TWO, SUPERSCRIPT_TWO])
def test_read_version_property_refuses_non_ascii_digits(tmp_path, value):
    folder = _built_twice(tmp_path, "docx")
    copy = tmp_path / "report-reviewed.docx"
    _rewrite(folder / "v1" / "report.docx", copy, value)
    assert read_version_property(copy) is None


def test_read_version_property_still_reads_ascii_digits(tmp_path):
    folder = _built_twice(tmp_path, "docx")
    copy = tmp_path / "report-reviewed.docx"
    _rewrite(folder / "v1" / "report.docx", copy, "12")
    assert read_version_property(copy) == 12


@pytest.mark.parametrize("value", [ARABIC_INDIC, ARABIC_INDIC_TWO, SUPERSCRIPT_TWO])
def test_a_copy_with_non_ascii_digits_is_compared_with_the_latest_version(tmp_path, value):
    folder = _built_twice(tmp_path, "docx")
    copy = tmp_path / "report-reviewed.docx"
    _rewrite(folder / "v1" / "report.docx", copy, value)
    code, plan = _read(copy, folder, 2)
    assert code == 0
    assert plan["version"] == 2
    warnings = [w for w in plan["warnings"] if w["code"] == "version_assumed"]
    assert len(warnings) == 1
    assert "no version property" in warnings[0]["message"]
