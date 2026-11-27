"""Issue 390: capacity warnings advise the writer without refusing a replacement."""

import re

import pytest

from ai_docs_kit.cli import main


def _block(title, count, body, sub, intent):
    items = [f"- **evidence** {body}\n  - {sub}" for _ in range(count)]
    return f'::: {{#a7c31 .section intent="{intent}"}}\n## ' + title + "\n\n" + "\n".join(items) + "\n:::\n"


@pytest.mark.parametrize("reverse", [False, True], ids=["target-first", "target-last"])
@pytest.mark.parametrize(
    ("fmt", "intent", "title_max", "items_max", "chars_max", "component"),
    [
        ("slides", "bullets", 8, 6, 140, "bullets"),
        ("doc", "bullets", 10, 40, 240, "bullet-list"),
        ("slides", "card-set", 8, 6, 140, "bullets"),
    ],
)
def test_put_warns_for_each_exceeded_limit_and_writes_the_new_block(
    tmp_path, capsys, reverse, fmt, intent, title_max, items_max, chars_max, component
):
    other = '::: {#other .section intent="bullets"}\n## Other evidence\n\n- Keep this separate.\n:::\n'
    # A card-set starts as cards; these replacements must use the bullets fallback.
    sections = [_block("Findings", 3 if intent == "card-set" else 1, "original evidence", "detail", intent), other]
    if reverse:
        sections.reverse()
    doctype = "report" if fmt == "doc" else "pitch-deck"
    working = tmp_path / "readout.md"
    working.write_text(
        f"---\ndoctype: {doctype}\nformat: {fmt}\n---\n\n## Sources\n\n"
        "- [S1] Illustrative evidence.\n\n" + "\n".join(sections),
        encoding="utf-8",
    )
    replacement = tmp_path / "block.md"
    # Head plus body counts towards item_chars; nested text does not.
    # All three measures are exactly at their maximum in the readable control.
    title = " ".join(["evidence"] * title_max)
    sub = "z" * (chars_max + 20)
    replacement.write_text(_block(title, items_max, "x" * (chars_max - 8), sub, intent), encoding="utf-8")
    assert main(["section", "put", str(working), "a7c31", "--from", str(replacement)]) == 0
    control = capsys.readouterr()
    assert "warning source.capacity" not in control.out + control.err

    title += " evidence"
    long_body = "x" * (chars_max - 7)
    replacement.write_text(_block(title, items_max + 1, long_body, sub, intent), encoding="utf-8")
    assert main(["section", "put", str(working), "a7c31", "--from", str(replacement)]) == 0
    captured = capsys.readouterr()
    # Check persistence before checking the currently missing advice.
    assert main(["section", "get", str(working), "a7c31"]) == 0
    saved = capsys.readouterr().out
    assert title in saved
    assert saved.count(long_body) == items_max + 1
    assert saved.count(sub) == items_max + 1
    assert "Keep this separate." in working.read_text(encoding="utf-8")
    lines = [line for line in (captured.out + captured.err).splitlines() if line.startswith("warning source.capacity ")]
    assert len(lines) == 3, "warn once for each exceeded limit, while still saving the block"
    for measure, maximum in [("title_words", title_max), ("items", items_max), ("item_chars", chars_max)]:
        matching = [line for line in lines if re.search(rf"\b{measure}\b", line)]
        assert len(matching) == 1, lines
        assert "a7c31" in matching[0] and component in matching[0]
        assert re.search(rf"\b{maximum + 1}\b", matching[0]) and re.search(rf"\b{maximum}\b", matching[0])
