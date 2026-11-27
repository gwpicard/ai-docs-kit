"""Issue 366: judge content parity through build and check, with real outputs.

The issue's seeded-pair procedure and data.values-visible's custom main.typ
are the oracles. Deliberately incomplete renderers and Word writers seed
losses at the output boundary; the commands still do the checking themselves.
"""

import json
import shutil
from pathlib import Path

import pytest
from docx import Document as WordDocument

from ai_docs_kit import building, cli
from ai_docs_kit.checks import catalogue
from ai_docs_kit.render import word

RULE = "geo.text-present"
SEEDED = Path(__file__).parent / "fixtures" / "seeded-defects" / RULE
FRONT = "---\ndoctype: report\nformat: doc\ntitle: Access review\n---\n\n"
SOURCES = "## Sources\n\n- [S1] Synthetic survey register.\n- [S2] Synthetic workshop transcript.\n\n"
PARAGRAPHS = [
    "Neighbourhood services retain the route sketch.",
    "The survey register records each visit.",
    "The recommendation keeps access under review.",
]
HEADING = "Access findings"
HEAD = "Route checks"
BODY = "Keep the access record."
SUB = "Retain the signed route sketch."
TARGETS = [
    ("title", HEADING),
    ("paragraphs[2]", PARAGRAPHS[2]),
    ("items[0]", HEAD),
    ("items[0].body", BODY),
    ("items[0].sub[1]", SUB),
]


def _run(capsys, command, source, *options):
    code = cli.main([command, str(source), *map(str, options)])
    captured = capsys.readouterr()
    assert captured.err == "", (code, captured.out, captured.err)
    assert code in (0, 1), (code, captured.out)
    return code, captured.out


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _hits(findings):
    return [finding for finding in findings if finding["rule_id"] == RULE]


def _build(capsys, source, *options):
    code, output = _run(capsys, "build", source, *options)
    assert code == 0, output  # Ordinary builds report errors without gating.
    version = Path(output.splitlines()[-1])
    assert (version / f"{source.stem}.pdf").is_file(), output
    assert (version / f"{source.stem}.docx").is_file(), output
    return version, output, _read(version / "findings.json")


def _check(capsys, source):
    code, output = _run(capsys, "check", source)
    return code, output, _read(source.parent / "build" / f"{source.stem}.findings.json")


def _section(ident, intent, blocks):
    return f'::: {{#{ident} .section intent="{intent}"}}\n' + "\n\n".join(blocks) + "\n:::\n\n"


def _source(tmp_path, interleaved=False):
    bullet = f"- **{HEAD}** {BODY}\n  - Confirm the boundary.\n  - {SUB}"
    blocks = [f"## {HEADING}", *PARAGRAPHS, bullet, "- Confirm the next visit."]
    if interleaved:
        blocks = [blocks[0], bullet, PARAGRAPHS[0], "- Confirm the next visit.", *PARAGRAPHS[1:]]
    main = _section("access", "bullets", blocks)
    other = _section("context", "body", ["## Survey context", "The register supplies the supporting evidence."])
    source = tmp_path / "report.md"
    source.write_text(FRONT + SOURCES + (other + main if interleaved else main + other), encoding="utf-8")
    return source


def _assert_clean(capsys, source):
    version, output, findings = _build(capsys, source)
    assert _hits(findings) == [], output
    assert RULE not in output
    code, output, findings = _check(capsys, source)
    assert code == 0 and _hits(findings) == [], output
    return version


def _assert_finding(finding, field, text, *, word_copy=False):
    assert finding["section_id"] == "access", finding
    assert (finding["severity"], finding["tier"], finding["format"]) == ("error", "geometry", "doc")
    # A list may be reported as one block including its sub-lines, or the
    # finding may locate the particular missing part within that item.
    reported_field = field.split(".")[0] if field.startswith("items[") else field
    assert reported_field in finding["message"], finding
    excerpts = [" ".join(text.split()[:3])]
    if field.startswith("items["):
        excerpts.append(HEAD)
    assert any(excerpt in finding["message"] for excerpt in excerpts), finding
    assert ("Word copy" in finding["message"]) is word_copy, finding


def _assert_recorded(version, output, findings):
    errors = [finding for finding in findings if finding["severity"] == "error"]
    manifest = _read(version / "manifest.json")
    assert manifest["findings"]["error"] == len(errors) >= len(_hits(findings)) > 0
    assert manifest["look"]["clean"] is False, "A missing block must prevent a clean look record"
    for finding in _hits(findings):
        assert f"error {RULE} access {finding['message']}" in output.splitlines(), output


def _use_main(monkeypatch, text):
    assemble = building.assemble

    def seeded_main(comp, dest, **kwargs):
        assemble(comp, dest, **kwargs)
        # This is an authored fixture source, leaving generated main.typ intact.
        main = dest / "text-present-fixture.typ"
        main.write_text(text, encoding="utf-8")
        return main

    monkeypatch.setattr(building, "assemble", seeded_main)


def _omit_pdf(monkeypatch, field):
    assemble = building.assemble
    fields = (field,) if isinstance(field, str) else field

    def incomplete_renderer(comp, dest, **kwargs):
        drawn = comp.model_copy(deep=True)
        section = next(section for section in drawn.sections if section.id == "access")
        for field in fields:
            if field == "title":
                section.props["title"] = ""
            elif field.startswith("paragraphs["):
                section.props["content_order"] = [entry for entry in section.props["content_order"] if entry != field]
            elif field == "items[0]":
                section.props["items"][0]["head"] = ""
            elif field == "items[0].body":
                section.props["items"][0]["body"] = ""
            elif field == "items[0].sub[1]":
                section.props["items"][0]["sub"] = section.props["items"][0]["sub"][:1]
            else:
                raise AssertionError(f"Unknown seeded field: {field}")
        return assemble(drawn, dest, **kwargs)

    monkeypatch.setattr(building, "assemble", incomplete_renderer)


def _remove_word_text(path, text):
    document = WordDocument(path)
    matches = [paragraph for paragraph in document.paragraphs if text in paragraph.text]
    assert len(matches) == 1, (text, [paragraph.text for paragraph in document.paragraphs])
    paragraph = matches[0]
    paragraph.text = paragraph.text.replace(text, "")
    document.save(path)


def _omit_word(monkeypatch, text):
    write_docx = word.write_docx

    def incomplete_writer(path, **kwargs):
        result = write_docx(path, **kwargs)
        _remove_word_text(result, text)
        return result

    monkeypatch.setattr(word, "write_docx", incomplete_writer)


def test_seeded_pair_runs_through_build_and_check(tmp_path, monkeypatch, capsys):
    assert (SEEDED / "fail" / "doc.md").is_file()
    assert (SEEDED / "pass" / "doc.md").is_file()
    assert (SEEDED / "fail" / "main.typ").is_file()
    assert (SEEDED / "fail" / "doc.md").read_bytes() == (SEEDED / "pass" / "doc.md").read_bytes()
    paths = {}
    for name in ("pass", "fail"):
        folder = tmp_path / name
        shutil.copytree(SEEDED / name, folder)
        paths[name] = folder / "doc.md"
    _assert_clean(capsys, paths["pass"])
    with monkeypatch.context() as seeded:
        _use_main(seeded, (SEEDED / "fail" / "main.typ").read_text(encoding="utf-8"))
        version, output, findings = _build(capsys, paths["fail"])
        checked = _check(capsys, paths["fail"])
    facts = _read(version / "layout.json")
    assert "Neighbourhood" not in " ".join(word["text"] for word in facts["words"])
    assert "Neighbourhood" in " ".join(p.text for p in WordDocument(version / "doc.docx").paragraphs)
    hits = _hits(findings)
    assert len(hits) == 1, "The seeded build must report its one omitted paragraph"
    _assert_finding(hits[0], "paragraphs[0]", "Neighbourhood services must retain the route sketch.")
    assert len([line for line in output.splitlines() if line.startswith(f"error {RULE} ")]) == 1
    _assert_recorded(version, output, findings)
    code, checked_output, checked_findings = checked
    assert code == 1 and len(_hits(checked_findings)) == 1, checked_output
    rules = [rule for rule in catalogue.all_rules() if rule.id == RULE]
    assert len(rules) == 1, "Register the rule exactly once in the built-in catalogue"
    assert rules[0].severity == "error" and rules[0].tier == "geometry"


@pytest.mark.parametrize("interleaved", [False, True], ids=["prose-first", "interleaved-context-first"])
@pytest.mark.parametrize("field,text", TARGETS)
def test_pdf_loss_names_the_block_and_fails_check(tmp_path, monkeypatch, capsys, interleaved, field, text):
    source = _source(tmp_path, interleaved)
    _assert_clean(capsys, source)
    with monkeypatch.context() as seeded:
        _omit_pdf(seeded, field)
        version, output, findings = _build(capsys, source)
        code, checked_output, checked_findings = _check(capsys, source)
    hits = _hits(findings)
    assert len(hits) == 1, f"Expected one PDF loss for {field}, got {hits}"
    _assert_finding(hits[0], field, text)
    _assert_recorded(version, output, findings)
    assert code == 1, checked_output
    assert len(_hits(checked_findings)) == 1, checked_findings
    _assert_finding(_hits(checked_findings)[0], field, text)
    assert f"error {RULE} access " in checked_output


@pytest.mark.parametrize("interleaved", [False, True], ids=["prose-first", "interleaved-context-first"])
def test_check_detects_a_paragraph_removed_from_existing_word_copy(tmp_path, capsys, interleaved):
    source = _source(tmp_path, interleaved)
    version = _assert_clean(capsys, source)
    copy = source.parent / "build" / "report.docx"
    _remove_word_text(copy, PARAGRAPHS[2])
    before = copy.read_bytes()
    # The version and PDF remain complete; check must inspect the copy in build/.
    assert PARAGRAPHS[2] in " ".join(p.text for p in WordDocument(version / "report.docx").paragraphs)
    code, output, findings = _check(capsys, source)
    hits = _hits(findings)
    assert code == 1, "check silently accepted a paragraph removed from the Word copy"
    assert len(hits) == 1, findings
    _assert_finding(hits[0], "paragraphs[2]", PARAGRAPHS[2], word_copy=True)
    assert f"error {RULE} access " in output
    assert copy.read_bytes() == before, "check must not repair or replace the copy it is checking"


@pytest.mark.parametrize("field,text", TARGETS)
def test_build_records_word_loss_in_the_same_version(tmp_path, monkeypatch, capsys, field, text):
    source = _source(tmp_path, interleaved=True)
    _assert_clean(capsys, source)
    with monkeypatch.context() as seeded:
        _omit_word(seeded, text)
        version, output, findings = _build(capsys, source)
    hits = _hits(findings)
    assert len(hits) == 1, f"The build must check the Word copy's {field} before saving its findings"
    _assert_finding(hits[0], field, text, word_copy=True)
    _assert_recorded(version, output, findings)
    assert text in " ".join(word["text"] for word in _read(version / "layout.json")["words"])


def test_one_block_missing_from_both_outputs_has_two_open_errors(tmp_path, monkeypatch, capsys):
    source = _source(tmp_path)
    _assert_clean(capsys, source)
    with monkeypatch.context() as seeded:
        _omit_pdf(seeded, "paragraphs[2]")
        _omit_word(seeded, PARAGRAPHS[2])
        version, output, findings = _build(capsys, source)
        final_code, final_output = _run(capsys, "build", source, "--final")
    hits = _hits(findings)
    assert len(hits) == 2, "PDF and Word losses of the same block must remain separate findings"
    assert len({finding["id"] for finding in hits}) == 2
    assert len({finding["fingerprint"] for finding in hits}) == 2
    for finding in hits:
        _assert_finding(finding, "paragraphs[2]", PARAGRAPHS[2], word_copy="Word copy" in finding["message"])
    assert sum("Word copy" in finding["message"] for finding in hits) == 1
    _assert_recorded(version, output, findings)
    assert final_code == 1 and "not ready: 2 error findings" in final_output, final_output


def test_two_missing_paragraphs_in_one_section_remain_distinct(tmp_path, monkeypatch, capsys):
    source = _source(tmp_path, interleaved=True)
    _assert_clean(capsys, source)
    with monkeypatch.context() as seeded:
        _omit_pdf(seeded, ("paragraphs[0]", "paragraphs[2]"))
        version, output, findings = _build(capsys, source)
        code, checked_output, checked_findings = _check(capsys, source)
    hits = _hits(findings)
    assert len(hits) == 2, "Every missing paragraph needs its own finding, even within one section"
    assert len({finding["id"] for finding in hits}) == 2
    assert len({finding["fingerprint"] for finding in hits}) == 2
    for index in (0, 2):
        matches = [finding for finding in hits if f"paragraphs[{index}]" in finding["message"]]
        assert len(matches) == 1, hits
        _assert_finding(matches[0], f"paragraphs[{index}]", PARAGRAPHS[index])
    _assert_recorded(version, output, findings)
    assert code == 1 and len(_hits(checked_findings)) == 2, checked_output


@pytest.mark.parametrize("interleaved", [False, True], ids=["prose-first", "list-first"])
def test_normalised_multisection_control_then_a_real_loss(tmp_path, monkeypatch, capsys, interleaved):
    paragraph = "Neighbourhood [S1 p.4] services retain [S2, 00:41] the route sketch."
    multiline = "```paragraph\n|-\n  The reorganisation keeps\n  access    clear.\n```"
    item = "- **Route checks** Keep the access record. [S1 p.4]\n  - Retain the signed route sketch. [S2, 00:41]"
    blocks = ["## Access findings", paragraph, multiline, item]
    if interleaved:
        blocks = [blocks[0], item, paragraph, multiline]
    extra = [
        _section("context", "body", ["## Survey context", "The register supplies the supporting evidence."]),
        _section("limits", "callout", ["## Survey limits", "Keep the uncertainty visible.", "- Repeat the visit."]),
        _section(
            "coverage",
            "key-numbers",
            ["## Survey coverage", "The register covers the pilot.", "- **42%** Coverage [S1 p.4]"],
        ),
        _section(
            "routes",
            "chart",
            [
                "## Route comparison",
                "Both districts retain their access record.",
                "```data\ntype: bar\ncategories: [Upland, Lowland]\n"
                "series:\n  - name: Visits\n    values: [17, 29]\n```",
                "> source: Synthetic survey register",
            ],
        ),
    ]
    source = tmp_path / "report.md"
    source.write_text(FRONT + SOURCES + _section("access", "bullets", blocks) + "".join(extra), encoding="utf-8")
    _assert_clean(capsys, source)
    # A real renderer splits words across physical lines. Source citations occur
    # inside prose, while cite.typ draws item citations with a space, not a comma.
    main = """#import "/lib/theme.typ": colour, page-setup, type-style
#import "/lib/marks.typ": section, el-full-width
#import "/lib/doc-content.typ": doc-list-item
#import "/components/body.typ": body
#import "/components/callout.typ": callout
#import "/components/key-figures-strip.typ": key-figures-strip
#import "/components/chart-table.typ": chart-table
#show: page-setup.with("doc")
#set text(fill: colour("ink"))
#let comp = json("/composition.json")
#let sec = comp.sections.at(0).props + comp.sections.at(0).content
#section(sec.id, {
  set text(..type-style("doc", "body"))
  el-full-width("heading", sec.id, field: "title", sec.title)
  el-full-width("paragraph", sec.id, field: "paragraphs[0]", par([
    Neigh-#linebreak()bourhood services retain the route sketch.
  ]))
  REORGANISATION
  doc-list-item(sec, 0)
})
#let sec = comp.sections.at(1).props + comp.sections.at(1).content
#body(sec)
#let sec = comp.sections.at(2).props + comp.sections.at(2).content
#callout(sec)
#let sec = comp.sections.at(3).props + comp.sections.at(3).content
#key-figures-strip(sec)
#let sec = comp.sections.at(4).props + comp.sections.at(4).content
#chart-table(sec)
"""
    complete = main.replace(
        "REORGANISATION",
        'el-full-width("paragraph", sec.id, field: "paragraphs[1]", '
        "par([The reorgani-#linebreak()sation keeps access clear.]))",
    )
    with monkeypatch.context() as seeded:
        _use_main(seeded, complete)
        version = _assert_clean(capsys, source)
    words = _read(version / "layout.json")["words"]
    assert "Neigh-" in [word["text"] for word in words]
    assert "reorgani-" in [word["text"] for word in words]
    with monkeypatch.context() as seeded:
        _use_main(seeded, main.replace("REORGANISATION", ""))
        version, output, findings = _build(capsys, source)
        code, checked_output, checked_findings = _check(capsys, source)
    hits = _hits(findings)
    assert len(hits) == 1, "Ignore wrapping, line-end hyphens, whitespace and citations, but detect lost prose"
    _assert_finding(hits[0], "paragraphs[1]", "The reorganisation keeps access clear.")
    _assert_recorded(version, output, findings)
    assert code == 1 and len(_hits(checked_findings)) == 1, checked_output
