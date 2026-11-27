# Changelog

Release entries are newest first, headed `## X.Y.Z`. Each entry records changes
to the surfaces named in PLAN.md, including working-file and version formats.
Use `### Added`, `### Changed` and `### Fixed` as needed. Prefix any incompatible
change with `Breaking:` and explain what callers or existing files must change.

## 0.1.0

First release baseline, for the `v0.1.0` tag.

### Command line

- `ai-docs-kit --version` prints `ai_docs_kit 0.1.0`.
- `build <name>.md` renders a PDF, runs checks, rasterises pages, writes an
  editable copy and saves a version. Its output names the PDF and version folder,
  error findings and gaps. A normal build can return exit 0 with findings;
  `--final` returns exit 1 when the final checks fail.
- `look <version> --pages` lists pages, sections and engine findings;
  `--findings <file>` validates and records the look agent's JSON findings.
  Exactly one option is required. Recording findings prints a summary naming
  open errors and pages not looked at.
- `review read <copy>` reads Word or PowerPoint wording, comments and structural
  changes into a JSON review plan. `review apply <name>.md --plan <file>` applies
  decided wording and structural changes, records redraft asks and reports what
  changed, including sections changed or missing since the copy's version.
- `rule test <rule> --example <version>/<section>` requires a proposed rule to
  fire on its example and no approved exemplar. `rule adopt` adds a tested rule
  to the rulebook on probation.
- `brand` provides brand initialisation, material intake, extraction, token
  changes, specimens, calibration and change history. `doctor` prints the local
  Python, Typst and API-key availability checks.
- Other commands are `init`, `check`, `write`, `section list`, `section get`,
  `section brief`, `section put`, `facts add`, `facts list`, `theme test`,
  `eval heal` and `eval critic`. Each command exposes its arguments with `--help`.
- Exit codes and text output are part of the command surface: commands generally
  return 0 on success, 1 for a failed check or refused operation and 2 for invalid
  input or a build error. Diagnostics may be on stderr; findings and summaries
  are on stdout. There is no `sent` command or sent-state workflow.

### Working-file and version formats

- The working file is UTF-8 Markdown (`<name>.md`) with YAML front matter,
  reserved `## Context` and `## Sources` blocks, and fenced `.section` blocks.
  Each section has a stable id and an intent; its content includes headings,
  paragraphs, items, citations, notes and optional YAML data. Ownership and lock
  attributes protect wording. Appearance belongs to the theme.
- Builds are numbered independently of engine releases under
  `<name>.versions/vN/`. Each contains the PDF, editable copy, `manifest.json`,
  `composition.json`, `layout.json`, `findings.json` and `pages/` with page images,
  `pages.json`, a contact sheet or spreads. The manifest records engine, Typst
  and theme versions, document revision, outputs, findings, gaps and the look
  record. Build outputs are snapshots; `look` can update the manifest's look
  record. Review copies identify their originating build version.

### Review readers and editable copies

- Word (`.docx`) and PowerPoint (`.pptx`) readers accept external review copies,
  including comments and tracked wording where supported. Malformed, oversized
  or hostile archives are refused with diagnostics.
- PowerPoint copies use a text-hidden page picture with native editable text
  fields and tables named `<section-id>/<field-path>`. Word copies hold text and
  lists in section bookmarks, with references for tables, charts and figures;
  long or invalid bookmark names are encoded, with a stored map for hashed names.
  Formatting changes become hints rather than copied styling. The PDF remains
  the deliverable and the working file remains the editable source of truth.

### Rulebook, renderer, skills and agents

- The rulebook combines the engine catalogue and the brand's rules and voice.
  Checks report source, geometry and pixel findings, with seeded-defect fixtures
  and passing controls. Proposed rules are tested before adoption on probation.
- Typst components and the chooser turn section intents into a composition;
  layout facts retain section and field marks for checks and editable copies.
  Golden files record component layout facts and are regenerated from source.
- The `brand`, `create` and `review` skills orchestrate the engine through
  `bin/ai-docs-kit`. Agents gather facts, draft sections, look at rendered pages
  and classify review items using the session's Claude. Skills read the brand's
  rulebook and `preferences.md`; the person's brand folder, working files and
  versions stay separate from the plugin files replaced on update.
