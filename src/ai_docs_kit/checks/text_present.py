"""Detect document text lost between the working file and either output."""

import re
from collections.abc import Iterator

from docx import Document as WordDocument

from ai_docs_kit.checks.engine import CheckContext, finding_key, make_finding, register, section_key
from ai_docs_kit.facts.layout import LayoutFacts
from ai_docs_kit.model import Finding, Provenance, Remedy, Rule, Section
from ai_docs_kit.model.rules import Scope, Tier
from ai_docs_kit.source.parser import CITATION

LINE_HYPHEN = re.compile(r"(?<=\w)[-\u2010\u00ad]\s*\n\s*(?=\w)")


def _normalise(text: str) -> str:
    text = LINE_HYPHEN.sub("", text)
    return " ".join(CITATION.sub(" ", text).split())


def _pdf_text(facts: LayoutFacts) -> str:
    parts: list[str] = []
    previous = None
    for word in facts.words:
        if previous is not None:
            # Preserve physical line ends until discretionary hyphens are removed.
            line_end = word.box.page != previous.box.page or abs(word.baseline - previous.baseline) > 1
            parts.append("\n" if line_end else " ")
        parts.append(word.text)
        previous = word
    # A physical line-end hyphen may be inserted or belong to a compound word.
    # Keep its position so matching can accept either without dropping other hyphens.
    return _normalise(LINE_HYPHEN.sub("\u00ad", "".join(parts)))


def _present(text: str, actual: str) -> bool:
    if text in actual:
        return True
    if "\u00ad" not in actual:
        return False
    pattern = "\u00ad?".join(f"[{char}\u00ad]" if char in "-\u2010" else re.escape(char) for char in text)
    return re.search(pattern, actual) is not None


def _blocks(section: Section) -> Iterator[tuple[str, str]]:
    if section.title:
        yield "title", section.title
    for index, paragraph in enumerate(section.paragraphs):
        yield f"paragraphs[{index}]", paragraph
    for index, item in enumerate(section.items):
        # Heads and sub-lines have different separators in PDF and Word.
        if item.head:
            yield f"items[{index}].head", item.head
        yield f"items[{index}].body", item.body
        for sub_index, sub in enumerate(item.sub):
            yield f"items[{index}].sub[{sub_index}]", sub


@register("text-present")
class TextPresent:
    tier: Tier = "geometry"

    def run(self, ctx: CheckContext, rule: Rule) -> list[Finding]:
        if ctx.doc.format != "doc" or ctx.facts is None:
            return []
        outputs = {"PDF": _pdf_text(ctx.facts)}
        if ctx.word_copy is not None:
            document = WordDocument(str(ctx.word_copy))
            outputs["Word copy"] = _normalise("\n".join(paragraph.text for paragraph in document.paragraphs))
        findings = []
        for index, section in enumerate(ctx.doc.sections):
            for field, raw in _blocks(section):
                text = _normalise(raw)
                if not text:
                    continue
                for output, actual in outputs.items():
                    if _present(text, actual):
                        continue
                    excerpt = " ".join(text.split()[:8])
                    findings.append(
                        make_finding(
                            rule,
                            ctx,
                            section_id=section_key(section, index),
                            message=f'{field} missing from {output}: "{excerpt}"',
                            measured={"field": field, "text": text, "output": output},
                            key=finding_key(section, index, f"{output}:{field}"),
                        )
                    )
        return findings


RULES = [
    Rule(
        id="geo.text-present",
        title="Every section text block appears in the PDF and Word copy",
        origin="manual",
        strength="hard",
        status="active",
        severity="error",
        tier="geometry",
        scope=Scope(format="doc"),
        check={"kind": "text-present"},
        remedy=Remedy.model_validate(
            {"class": "engine", "hint": "draw every section heading, paragraph and list item in both outputs"}
        ),
        provenance=Provenance(source={"doc": "docs/DESIGN.md", "section": "4"}),
    ),
]
