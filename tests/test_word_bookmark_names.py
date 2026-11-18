"""Bookmark names for section ids map back to the id."""

import pytest

from ai_docs_kit.review.word_read import bookmark_name, section_of


@pytest.mark.parametrize("section_id", ["beta01", "my-section", "a_b", "_x2d_", "1st", "Xenc_a", "é"])
def test_a_bookmark_name_maps_back_to_its_section(section_id):
    name = bookmark_name(section_id)
    assert name[0].isalpha() and name.replace("_", "").isalnum()
    assert section_of(name) == section_id


def test_a_valid_id_is_kept_as_it_is():
    assert bookmark_name("beta01") == "beta01"
