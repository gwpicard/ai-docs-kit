"""Each Word source regression pairs a control with an edit that exposed the defect."""

import pytest

from test_word_source_line_body_boundaries import (
    ORIGINAL,
    REFERENCE,
    REVISED,
)
from test_word_source_line_body_boundaries import (
    test_review_plan_and_apply_keep_body_boundaries as _body_round_trip,
)
from test_word_source_line_heading_free import (
    test_heading_free_body_clear_keeps_source_and_section as _heading_free_round_trip,
)


@pytest.mark.parametrize("control", ["unchanged-copy", "no-source"])
def test_source_body_edit_with_boundary_control(tmp_path, control):
    control_folder = tmp_path / "control"
    control_folder.mkdir()
    if control == "unchanged-copy":
        _body_round_trip(control_folder, [ORIGINAL], [ORIGINAL], REFERENCE)
    else:
        _body_round_trip(control_folder, [ORIGINAL, REFERENCE], [REVISED, REFERENCE], "")

    edited_folder = tmp_path / "edited"
    edited_folder.mkdir()
    # The shared round trip checks the plan, applied paragraphs and preserved source for both copies.
    _body_round_trip(edited_folder, [ORIGINAL], [REVISED], REFERENCE)


@pytest.mark.parametrize("with_list", [False, True], ids=["paragraph", "paragraph-and-list"])
def test_heading_free_clear_with_whole_section_deletion(tmp_path, with_list):
    deleted_folder = tmp_path / "deleted"
    deleted_folder.mkdir()
    _heading_free_round_trip(deleted_folder, remove_section=True, with_list=with_list)

    cleared_folder = tmp_path / "cleared"
    cleared_folder.mkdir()
    # Exercise retained-source clearing and accepted whole-section deletion in the same collected case.
    _heading_free_round_trip(cleared_folder, remove_section=False, with_list=with_list)
