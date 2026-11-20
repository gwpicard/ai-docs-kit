import ast
from pathlib import Path

from ai_docs_kit.checks import engine, source  # noqa: F401  (register checks)
from ai_docs_kit.checks.engine import CheckContext, make_finding, run_checks
from ai_docs_kit.facts.layout import LayoutFacts
from ai_docs_kit.model import Document, Item, Provenance, Remedy, Rule, Section

CHECKS_DIR = Path(__file__).resolve().parents[1] / "src" / "ai_docs_kit" / "checks"


def _rule(rule_id, tier, kind, severity="error"):
    return Rule(
        id=rule_id,
        title="t",
        origin="manual",
        strength="hard",
        status="active",
        severity=severity,
        tier=tier,
        check={"kind": kind},
        remedy=Remedy.model_validate({"class": "redraft", "hint": "h"}),
        provenance=Provenance(source={"doc": "DESIGN.md", "section": "1"}),
    )


class _DocumentFinding:
    tier = None

    def run(self, ctx, rule):
        return [make_finding(rule, ctx, message="about the document")]


class _EverySection:
    tier = None

    def run(self, ctx, rule):
        return [
            make_finding(
                rule,
                ctx,
                message="about a section",
                section_id=section.id,
                key=engine.finding_key(section, index),
            )
            for index, section in enumerate(ctx.doc.sections)
        ]


def _facts():
    return LayoutFacts(pdf_sha256="x", pages=[], words=[], shapes=[], marks=[])


def test_owner_is_the_section_id_for_a_section_with_one():
    doc = Document(
        front={"title": "T"},
        format="slides",
        sections=[Section(id="aaaa1", intent="bullets"), Section(id="aaaa2", intent="bullets")],
    )
    findings = run_checks([_rule("source.empty-section", "source", "empty-section")], CheckContext(doc=doc))
    assert [f.owner for f in findings] == ["aaaa1", "aaaa2"]


def test_owner_is_the_section_key_for_a_section_without_an_id():
    doc = Document(
        front={"title": "T"},
        format="slides",
        sections=[Section(intent="bullets", title="A", items=[Item(body="x")]), Section(intent="bullets")],
    )
    findings = run_checks([_rule("source.empty-section", "source", "empty-section")], CheckContext(doc=doc))
    assert [f.section_id for f in findings] == [None]
    assert [f.owner for f in findings] == ["section-1"]


def test_owner_is_none_for_a_document_finding(monkeypatch):
    monkeypatch.setitem(engine.CHECKS, "t191.document", _DocumentFinding())
    doc = Document(front={"title": "T"}, format="slides", sections=[Section(id="aaaa1", intent="bullets")])
    findings = run_checks([_rule("t191.document", "source", "t191.document")], CheckContext(doc=doc))
    assert len(findings) == 1
    assert findings[0].owner is None


def test_document_error_in_an_earlier_tier_does_not_hide_later_findings(monkeypatch):
    # #183: a document-level error has no owner, so it blocks no section and not the document.
    monkeypatch.setitem(engine.CHECKS, "t191.document", _DocumentFinding())
    monkeypatch.setitem(engine.CHECKS, "t191.sections", _EverySection())
    doc = Document(
        front={"title": "T"},
        format="slides",
        sections=[Section(id="aaaa1", intent="bullets"), Section(intent="bullets")],
    )
    rules = [
        _rule("t191.early", "source", "t191.document"),
        _rule("t191.later-section", "geometry", "t191.sections"),
        _rule("t191.later-document", "geometry", "t191.document"),
    ]
    findings = run_checks(rules, CheckContext(doc=doc, facts=_facts()))
    assert [f.rule_id for f in findings].count("t191.later-section") == 2
    assert "t191.later-document" in {f.rule_id for f in findings}
    assert "t191.early" in {f.rule_id for f in findings}


def test_section_error_still_blocks_that_sections_later_findings(monkeypatch):
    monkeypatch.setitem(engine.CHECKS, "t191.sections", _EverySection())
    doc = Document(
        front={"title": "T"},
        format="slides",
        sections=[Section(id="aaaa1", intent="bullets"), Section(intent="bullets")],
    )
    rules = [_rule("t191.early", "source", "t191.sections"), _rule("t191.later", "geometry", "t191.sections")]
    findings = run_checks(rules, CheckContext(doc=doc, facts=_facts()))
    assert {f.rule_id for f in findings} == {"t191.early"}


_ID_METHODS = {"get", "setdefault", "pop"}


def _is_section_id(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "id"
        and isinstance(node.value, ast.Name)
        and node.value.id in {"section", "s", "composed"}
    )


def _offences(tree: ast.AST) -> list[int]:
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            lines += [k.lineno for k in node.keys if k is not None and _is_section_id(k)]
        elif isinstance(node, ast.DictComp) and _is_section_id(node.key):
            lines.append(node.key.lineno)
        elif isinstance(node, ast.Subscript) and _is_section_id(node.slice):
            lines.append(node.lineno)
        elif isinstance(node, ast.keyword) and node.arg == "key" and _is_section_id(node.value):
            lines.append(node.value.lineno)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _ID_METHODS
            and node.args
            and _is_section_id(node.args[0])
        ):
            lines.append(node.lineno)
    return lines


def test_checks_never_key_a_finding_or_dict_by_section_id():
    found = []
    for path in sorted(CHECKS_DIR.glob("*.py")):
        found += [f"{path.name}:{line}" for line in _offences(ast.parse(path.read_text()))]
    assert found == [], "use section_key, not section.id, as a key"
