"""`review read` on a PowerPoint copy: replies in a modern comment thread (`p188:replyLst`, [MS-PPTX] 2.3.4).

Plan shape these tests pin: each reply is a comment item on the parent's section and slide, with its own
`author` and `text` and `reply_to` set to the parent's `id`; a modern comment item carries its `id`.
"""

# ruff: noqa: F811
import json
import re
from pathlib import Path

from tests.test_review_read_pptx import (  # noqa: F401  (the fixtures are used by name)
    _deck_copy,
    _legacy_parts,
    _modern_parts,
    _plan,
    _section,
    sent,
    work,
)

PARENT = "{11111111-1111-1111-1111-111111111111}"
KNOWN = "{22222222-2222-2222-2222-222222222222}"
OTHER = "{33333333-3333-3333-3333-333333333333}"
GONE = "{99999999-9999-9999-9999-999999999999}"


def _reply(identifier: str, author: str, text: str) -> str:
    return (
        f'<p188:reply id="{identifier}" authorId="{author}" created="2026-11-17T10:00:00.000">'
        f'<p188:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr lang="en-GB"/><a:t>{text}</a:t></a:r></a:p>'
        "</p188:txBody></p188:reply>"
    )


def _with_replies(parts: dict[str, bytes], replies: list[str]) -> dict[str, bytes]:
    """`parts` with the modern comment's reply list set, and a second known author added."""
    name = "ppt/comments/modernComment_100_1.xml"
    text = parts[name].decode()
    if replies:
        text = text.replace("</p188:cm>", "<p188:replyLst>" + "".join(replies) + "</p188:replyLst></p188:cm>")
    authors = (
        parts["ppt/authors.xml"]
        .decode()
        .replace(
            "</p188:authorLst>",
            f'<p188:author id="{OTHER}" name="Second Reviewer" initials="SR" userId="S::sr@example.test::1"'
            ' providerId="AD"/></p188:authorLst>',
        )
    )
    return {**parts, name: text.encode(), "ppt/authors.xml": authors.encode()}


def _threaded(work, slide, shape, replies):
    parts = _modern_parts(work, slide, "Modern Author", "Is this the right order?", shape)
    return _deck_copy(work, parts=_with_replies(parts, replies))


def test_each_reply_becomes_a_comment_item_linked_to_its_parent(work, capsys):
    replies = [
        _reply("{aaaaaaaa-0000-0000-0000-000000000001}", OTHER, "Yes, keep it."),
        _reply("{aaaaaaaa-0000-0000-0000-000000000002}", KNOWN, "Then move the date up."),
    ]
    plan = _plan(_threaded(work, 2, "agenda/title", replies), capsys)
    items = _section(plan, "agenda")["confirm"]
    assert [i["kind"] for i in items] == ["comment"] * 3
    parent = next(i for i in items if i.get("reply_to") is None)
    assert parent["id"] == PARENT
    assert parent["author"] == "Modern Author"
    found = [(i["author"], i["text"], i["reply_to"], i["slide"], i["shape"]) for i in items if i is not parent]
    assert sorted(found) == sorted(
        [
            ("Second Reviewer", "Yes, keep it.", PARENT, 2, "agenda/title"),
            ("Modern Author", "Then move the date up.", PARENT, 2, "agenda/title"),
        ]
    )


def test_replies_stay_on_the_parents_section_for_a_slide_comment(work, capsys):
    replies = [_reply("{aaaaaaaa-0000-0000-0000-000000000003}", OTHER, "Agreed.")]
    plan = _plan(_threaded(work, 1, None, replies), capsys)
    items = _section(plan, "cover")["confirm"]
    assert sorted(i["text"] for i in items) == ["Agreed.", "Is this the right order?"]
    assert all(i["slide"] == 1 for i in items)
    assert [i["reply_to"] for i in items if i["text"] == "Agreed."] == [PARENT]
    for name, other in plan["sections"].items():
        if name != "cover":
            assert not other.get("confirm"), name


def test_a_reply_by_an_unknown_author_has_a_null_author(work, capsys):
    replies = [_reply("{aaaaaaaa-0000-0000-0000-000000000004}", GONE, "Who wrote this?")]
    plan = _plan(_threaded(work, 2, "agenda/title", replies), capsys)
    items = _section(plan, "agenda")["confirm"]
    reply = next(i for i in items if i["text"] == "Who wrote this?")
    assert reply["author"] is None
    assert reply["reply_to"] == PARENT


def test_a_modern_comment_without_replies_has_no_reply_item(work, capsys):
    plan = _plan(_threaded(work, 2, "agenda/title", []), capsys)
    items = _section(plan, "agenda")["confirm"]
    assert len(items) == 1
    assert items[0]["id"] == PARENT
    assert items[0].get("reply_to") is None


def test_a_legacy_comment_is_not_a_reply(work, capsys):
    copy = _deck_copy(work, parts=_legacy_parts(work, 2, "Legacy Author", "Old-style note."))
    items = _section(_plan(copy, capsys), "agenda")["confirm"]
    assert [(i["author"], i["text"], i.get("reply_to")) for i in items] == [("Legacy Author", "Old-style note.", None)]


def test_the_schema_names_reply_to():
    schema = Path(__file__).resolve().parents[1] / "docs" / "schemas" / "review" / "ReviewPlan.schema.json"
    text = schema.read_text(encoding="utf-8")
    assert "reply_to" in text
    comment = json.loads(text)["$defs"]["CommentItem"]["properties"]
    assert "reply_to" in comment
    assert re.search(r"null", json.dumps(comment["author"]))
