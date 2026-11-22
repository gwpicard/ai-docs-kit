"""Missing bookmark maps leave bullets unplaced through the review command, in either section order."""

import json
import zipfile

import pytest

from ai_docs_kit.cli import main


@pytest.mark.parametrize("missing_last", [False, True], ids=["missing-between-lists", "missing-after-lists"])
def test_review_read_reports_unresolved_list_without_changing_known_lists(tmp_path, missing_last):
    missing_id = "supporting_actions_" + "b" * 40
    opening = (
        '::: {#opening .section intent="body"}\n## Opening\n\n'
        "- Keep the opening action\n- Keep the opening follow-up\n:::\n\n"
    )
    supporting = (
        f'::: {{#{missing_id} .section intent="body"}}\n'
        "- Keep the separate supporting action\n- Keep the separate follow-up\n:::\n\n"
    )
    closing = '::: {#closing .section intent="body"}\n## Closing\n\n- Keep the closing action\n:::\n'
    source = tmp_path / "report.md"
    source.write_text(
        "---\ndoctype: report\nformat: doc\ntitle: Review note\n---\n\n"
        + opening
        + (closing + "\n" + supporting if missing_last else supporting + closing),
        encoding="utf-8",
    )
    assert main(["build", str(source)]) == 0
    version = tmp_path / "report.versions" / "v1"
    sent = version / "report.docx"
    reviewed = tmp_path / "report-reviewed.docx"
    reviewed.write_bytes(sent.read_bytes())

    # The intact map is the passing control for both arrangements of the same sections.
    assert main(["review", "read", str(reviewed)]) == 0
    plan_path = version / "review-plan.json"
    before = json.loads(plan_path.read_text(encoding="utf-8"))
    assert set(before["sections"]) == {"opening", missing_id, "closing"}
    assert before["confirm"] == []
    assert all(section["items"] is None and section["owner"] is None for section in before["sections"].values())

    with zipfile.ZipFile(sent) as archive, zipfile.ZipFile(reviewed, "w", zipfile.ZIP_DEFLATED) as target:
        for name in archive.namelist():
            if name != "docProps/custom.xml":
                target.writestr(name, archive.read(name))

    assert main(["review", "read", str(reviewed)]) == 0
    after = json.loads(plan_path.read_text(encoding="utf-8"))
    unplaced = "\n".join(item["text"] for item in after["confirm"] if item["kind"] == "unplaced")
    for text in ("Keep the separate supporting action", "Keep the separate follow-up"):
        assert text in unplaced, f"The review plan lost an unresolved section's bullet: {after}"
    for section_id in ("opening", "closing"):
        section = after["sections"][section_id]
        assert section["items"] is None, f"An unresolved list changed {section_id}: {section}"
        assert section["wording"] is None
        assert section["title"] is None
        assert section["owner"] is None
