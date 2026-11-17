"""An unplaced item is report-only: `review apply` cannot place it, so it is never offered for acceptance."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = (ROOT / "skills" / "review" / "SKILL.md").read_text(encoding="utf-8")
AGENT = (ROOT / "agents" / "review-classify.md").read_text(encoding="utf-8")


def test_agent_does_not_call_an_unplaced_item_restructure():
    assert not re.search(r"`restructure` for every structural item", AGENT)
    assert re.search(r"`skip` for an `unplaced` item", AGENT)


def test_skill_only_reports_unplaced_items():
    assert re.search(r"`unplaced` item[^.\n]*only reported, never offered", SKILL)
