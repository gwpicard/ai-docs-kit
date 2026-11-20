"""An unresolved hashed bookmark must not leak its list into the preceding section."""

import zipfile

from ai_docs_kit.cli import main
from ai_docs_kit.review.word_read import read_word


def test_list_under_a_missing_hashed_bookmark_map_is_unplaced(tmp_path):
    section_id = "supporting_actions_" + "a" * 40
    source = tmp_path / "report.md"
    source.write_text(
        "---\ndoctype: report\nformat: doc\ntitle: Review note\n---\n\n"
        '::: {#opening .section intent="body"}\n## Opening\n\n'
        "- Keep the opening action\n:::\n\n"
        f'::: {{#{section_id} .section intent="body"}}\n'
        "- Keep the separate supporting action\n:::\n",
        encoding="utf-8",
    )
    assert main(["build", str(source)]) == 0
    sent = tmp_path / "report.versions" / "v1" / "report.docx"
    before = read_word(sent)
    assert before.items["opening"] == ["Keep the opening action"]
    assert before.items[section_id] == ["Keep the separate supporting action"]

    # A copy may lose its optional custom properties when saved by another editor.
    reviewed = tmp_path / "report-reviewed.docx"
    with zipfile.ZipFile(sent) as archive, zipfile.ZipFile(reviewed, "w", zipfile.ZIP_DEFLATED) as target:
        for name in archive.namelist():
            if name != "docProps/custom.xml":
                target.writestr(name, archive.read(name))

    after = read_word(reviewed, set(before.order))
    assert any("Keep the separate supporting action" in text for _, text in after.unplaced), (
        "Text with an unresolved hashed bookmark must be unplaced, "
        f"but it was assigned to a different section: {after.items}"
    )
    assert after.items["opening"] == ["Keep the opening action"]
