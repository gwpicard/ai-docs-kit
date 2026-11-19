"""Compatibility with Word plans written before headings and bodies were split."""

import re

from ai_docs_kit.model import Section
from ai_docs_kit.review.plan import ReviewPlan


def split_legacy_wording(plan: ReviewPlan, sections: list[Section]) -> None:
    """Normalise old wording once; an explicit title key identifies the new plan format."""
    titles = {section.id: section.title for section in sections}
    for section_id, item in plan.sections.items():
        if "title" in item.model_fields_set or not item.wording:
            continue
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", item.wording) if p.strip()]
        title = titles.get(section_id)
        if paragraphs and title and " ".join(paragraphs[0].split()) == " ".join(title.split()):
            item.wording = "\n\n".join(paragraphs[1:])
        item.title = None
