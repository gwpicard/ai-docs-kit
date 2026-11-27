# Python API

Import the public functions and result models from `ai_docs_kit.api`. The API is
synchronous, runs the engine's deterministic checks and makes no model calls.
It prints nothing. Paths accept either `pathlib.Path` objects or strings.

```python
from pathlib import Path
from ai_docs_kit.api import build, list_findings, list_versions, preview, read_document

path = Path("report.md")
document = read_document(path)
result = preview(path, Path("scratch/report"))
built = build(path)
findings = list_findings(built.version)
versions = list_versions(path)
```

| Function | Result | Behaviour |
|---|---|---|
| `read_document(path)` | `Document` | Front matter, format, context, sources, revision and every section field, in source order. Does not stamp ids or create project state. |
| `build(path, theme=None)` | `BuildResult` | Saves the next version and returns its path, absolute paths to its PDF and editable copy, and engine findings. |
| `preview(path, scratch, theme=None)` | `PreviewResult` | Renders every page in scratch and returns PNG paths, page regions, field boxes and engine findings. Writes no version or oplog entry and leaves the working file unchanged. |
| `list_findings(version)` | `list[Finding]` | Reads the engine findings stored in that version, even when the working file has changed or disappeared. |
| `list_versions(path)` | `list[Version]` | Reads version paths, numbers and manifests in ascending numeric order. Returns an empty list when no version folder exists. |
| `edit_fields(path, section_id, fields, base_rev)` | `EditResult` | Sets section fields and `owner="human"`, keeping the person's wording without a fact guard. |
| `add_section(path, after_id, section, base_rev)` | `EditResult` | Inserts a human-owned `Section` after the named section, or at the start when `after_id=None`. Allocates an id if absent without changing the input model. |
| `delete_section(path, section_id, base_rev)` | `EditResult` | Removes the section and returns its content with the new revision. |
| `move_section(path, section_id, after_id, base_rev)` | `EditResult` | Moves a section after the named section, keeping its content and id. |

Every edit writes one `author="human"` patch under the project lock. `EditResult`
holds `rev` and `section`. Use the revision from `read_document` for `base_rev`.
`PatchRejected` carries `code` and `message`, represented by the `EditError`
schema. A stale revision (`stale-base-rev`), missing section (`unknown-section`)
or target with `lock="all"` (`lock-all`) leaves the working file and history
unchanged. Identity, appearance and section validation guards still apply.

Builds, checks and previews compare section figures with the stored gathered
facts, sources and string front matter, including human-owned sections. Cited
figures use their source key and locator; uncited figures use all evidence.
The previous section wording never supplies evidence for this check. The older
writer facts store remains readable. Human-owned sections activate the check
even before facts are gathered. For older documents without human-owned
sections, the check remains inactive when neither facts store exists.

`theme=None` follows the working file's normal theme resolution. An explicit
folder overrides it. Source, geometry and pixel findings are included in both
builds and previews, including errors. Findings do not prevent saving a draft
build. Structural parse errors and rendering failures raise `ValueError`;
filesystem failures raise `OSError`; theme selection and validation failures
raise `ai_docs_kit.theme.ThemeError`.

Preview uses the normal composition, renderer and look. It caches layout facts
by rendered PDF content under scratch's `.ai_docs_kit/cache/facts/`, with a
composition signature so id-only changes refresh anchors. An identical second
preview reuses extraction. Checks still run on every preview.
Scratch must not contain the working file or lie inside its `.ai_docs_kit` or
`<name>.versions` folder. Use a dedicated scratch folder; rendering replaces its
`render/` directory. Previews do not write an editable copy.

Every result is a Pydantic model, with nested models for page regions and field
boxes. Coordinates use the layout facts' page units (points); field paths use
`FIELD_PATTERN`, with `front.title` and `front.audience` for title-block fields.
Use `model_dump(mode="json")`, `model_dump_json()` or `model_validate_json()`
for serialisation. The equivalent command-line JSON surfaces are:

```sh
ai-docs-kit section list report.md --json
ai-docs-kit section put report.md summary --from summary.md --json
ai-docs-kit build report.md --json
ai-docs-kit look report.versions/v1 --pages --json
```

`section put --json` prints `{"rev": 1, "section_id": "summary"}` after its
normal guarded replacement. The last command reads a `PreviewResult` from the
saved version without rebuilding it. Without `--json`, the commands retain
their text output and exit codes. `build --final --json` also retains the final
gate's exit code and keeps all output in the single JSON result.

Result schemas are pinned in `docs/schemas/api/`. After an intentional model
change, regenerate them from the source:

```sh
uv run python -c 'from pathlib import Path; from ai_docs_kit.api import export_api_schemas; export_api_schemas(Path("docs/schemas/api"))'
```

The acceptance tests compare every returned model's schema with its pin. New
fields must be optional with a fallback so previously saved results remain
readable.
