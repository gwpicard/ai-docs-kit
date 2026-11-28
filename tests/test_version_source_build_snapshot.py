"""Version source bytes must describe the build even after a concurrent edit."""

import pytest

from ai_docs_kit import api, building, cli
from ai_docs_kit.facts.layout import LayoutFacts
from ai_docs_kit.render.compose import Composition


@pytest.mark.parametrize(("format_", "entry"), [("doc", "cli"), ("slides", "cli"), ("doc", "api")])
def test_build_source_snapshot_matches_render_with_and_without_later_edit(
    tmp_path, capsys, monkeypatch, format_, entry
):
    compile_pdf = building.compile_pdf
    intent = "body" if format_ == "doc" else "statement"
    original = b"\xef\xbb\xbf" + (
        f"---\ndoctype: report\nformat: {format_}\n---\n\n"
        f"::: {{#first .section intent={intent} owner=ai}}\n"
        "## Original café wording\n\nThe agreed wording stays.\n:::\n"
    ).replace("\n", "\r\n").encode("utf-8")
    later = original.replace("Original café wording".encode(), "Later café wording".encode())
    # Each invocation pairs the unchanged control with the seeded concurrent edit.
    for edited in (False, True):
        root = tmp_path / ("edited" if edited else "unchanged")
        root.mkdir()
        path = root / "note.md"
        path.write_bytes(original)
        calls = []

        def compile_then_edit(*args, working=path, mutate=edited, renders=calls, **kwargs):
            result = compile_pdf(*args, **kwargs)
            renders.append(working)
            if mutate:
                working.write_bytes(later)
            return result

        with monkeypatch.context() as probe:
            probe.setattr(building, "compile_pdf", compile_then_edit)
            if entry == "cli":
                code = cli.main(["build", str(path), "--json"])
                output = capsys.readouterr()
                assert code == 0 and not output.err, output
                built = api.BuildResult.model_validate_json(output.out)
            else:
                built = api.build(path)

        assert calls == [path], "the edit must happen during the real render"
        expected_working = later if edited else original
        assert path.read_bytes() == expected_working, "building must preserve the later edit"
        version = built.version
        source = version / "source.md"
        composition = Composition.model_validate_json((version / "composition.json").read_bytes())
        facts = LayoutFacts.model_validate_json((version / "layout.json").read_bytes())
        assert composition.sections[0].props["title"] == "Original café wording"
        rendered = " ".join(word.text for word in facts.words)
        assert "Original café wording" in rendered and "Later café wording" not in rendered
        assert source.read_bytes() == original, "save the exact bytes parsed, including BOM, CRLF and bare attributes"
        assert [output.suffix for output in built.outputs] == [".pdf", ".docx" if format_ == "doc" else ".pptx"]

        if edited:
            before = api.read_document(path)
            restored = api.restore(path, "v1", before.rev)
            assert restored.sections == api.read_document(source).sections
            assert restored.sections[0].title == "Original café wording"
            api.undo(path, restored.rev)
            assert api.read_document(path).sections == before.sections
            assert source.read_bytes() == original
