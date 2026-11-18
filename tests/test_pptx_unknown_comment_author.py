"""`review read` on a PowerPoint copy: a comment whose author is not listed has `author: null`, never `""`."""

# ruff: noqa: F811
from tests.test_review_read_pptx import (  # noqa: F401  (the fixtures are used by name)
    _deck_copy,
    _legacy_parts,
    _modern_parts,
    _plan,
    _section,
    sent,
    work,
)

KNOWN = "{22222222-2222-2222-2222-222222222222}"
GONE = "{99999999-9999-9999-9999-999999999999}"


def _all_items(plan):
    return [i for s in plan["sections"].values() for i in s.get("confirm") or []]


def test_a_modern_comment_by_an_unlisted_author_has_a_null_author(work, capsys):
    parts = _modern_parts(work, 2, "Modern Author", "Who am I?", "agenda/title")
    name = "ppt/comments/modernComment_100_1.xml"
    parts[name] = parts[name].decode().replace(f'authorId="{KNOWN}"', f'authorId="{GONE}"').encode()
    plan = _plan(_deck_copy(work, parts=parts), capsys)
    items = _section(plan, "agenda")["confirm"]
    assert [(i["text"], i["author"]) for i in items] == [("Who am I?", None)]
    assert all(i["author"] != "" for i in _all_items(plan))


def test_a_modern_comment_by_a_listed_author_keeps_the_name(work, capsys):
    parts = _modern_parts(work, 2, "Modern Author", "Known.", "agenda/title")
    plan = _plan(_deck_copy(work, parts=parts), capsys)
    assert [i["author"] for i in _section(plan, "agenda")["confirm"]] == ["Modern Author"]


def test_a_legacy_comment_by_an_unlisted_author_has_a_null_author(work, capsys):
    parts = _legacy_parts(work, 2, "Legacy Author", "Who am I?")
    name = "ppt/comments/comment1.xml"
    parts[name] = parts[name].decode().replace('authorId="0"', 'authorId="7"').encode()
    plan = _plan(_deck_copy(work, parts=parts), capsys)
    items = _section(plan, "agenda")["confirm"]
    assert [(i["text"], i["author"]) for i in items] == [("Who am I?", None)]
    assert all(i["author"] != "" for i in _all_items(plan))
