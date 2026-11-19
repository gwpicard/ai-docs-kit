"""Word treats bookmark names as case-insensitive, so ids that differ only by case need distinct names."""

from ai_docs_kit.bookmark_names import bookmark_name


def test_ids_differing_by_case_get_names_distinct_ignoring_case():
    assert bookmark_name("Intro").lower() != bookmark_name("intro").lower()
