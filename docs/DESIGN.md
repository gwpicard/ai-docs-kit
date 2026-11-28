# ai-docs-kit: design

Claude skills that write branded reports and decks as PDF, check every build against a brand rulebook
and their own rendered pages, and learn from the comments a reviewer leaves in Word or PowerPoint.

The engine underneath (working file, components, chooser, checks, layout facts, versions, brand
ingestion) is described in `docs/ENGINE.md`. This file describes what wraps it: the skills, the
agents, the editable copies and the review round trip. Where the two differ, this file wins.

---

## 1. What it is

A person opens Claude Code in a folder holding whatever they have (a transcript, notes, a spreadsheet,
some slides, or nothing) and says what they need. The `create` skill agrees a document type and an
outline, drafts every section, builds the PDF, looks at every rendered page, fixes what it finds and
only then offers the version. Beside the PDF it writes an editable copy: a `.pptx` for a deck, a
`.docx` for a document. The reviewer edits text and leaves comments in that copy. The `review` skill
reads the copy back, applies the wording, redrafts what the comments asked for, rebuilds through the
same look, and offers the next version. The person repeats until they are happy.

A comment that states a lasting preference ("we never say 'leverage'") can become a rule in the brand
rulebook, so the next document does not need the same comment.

The `brand` skill builds the brand the other two use: tokens, voice, rules with their sources, and
components fitted to the brand, from the brand's guidelines, templates and approved examples.

## 2. Decisions

| # | Decision | Consequence |
|---|---|---|
| S1 | **The PDF is the deliverable.** The engine renders it with Typst, as before. | One renderer and one source of geometry for the checks. |
| S2 | **Every build also writes an editable copy**, for review only. | A reviewer uses the tool they know. The copy is never the deliverable and never the source of truth; edits come back through `review`. |
| S3 | **The PowerPoint copy looks like the slides.** Each slide shows exactly what the PDF slide shows, with every text field as a native, editable text box at its measured position. | The reviewer edits in context. See 5.1. |
| S4 | **The Word copy is the text.** Headings, paragraphs and lists, with a one-line reference in place of each table, chart or figure. | Reviewers comment on wording, which is what a document review is about. No attempt at page fidelity. |
| S5 | **Checks run on every build, never on request.** There is no separate check skill. | A version cannot reach a person without its look record. |
| S6 | **The session's Claude is the model.** Skills and agents make no API calls of their own. | No API key, no cassettes on the skill path. The engine stays deterministic. |
| S7 | **No version reaches a person unlooked-at.** A version is handed over with its look summary line, which names every open error and every page not looked at. | The person is never told a version is clean when it is not: the summary line states the open errors and the unlooked pages plainly. |
| S8 | **Formatting never round-trips.** Bold, colour, a resized box or a moved shape in a review copy is read as intent, never copied. | The brand cannot leak out through the review loop. |
| S9 | **Brand-neutral.** No third-party brand names, logos, fonts or images ship. | A neutral theme with an open-licensed font is the showcase. |
| S10 | **Two layers: the plugin and the person's layer.** The plugin (engine, skills, agents, component library, neutral theme) is shared code, replaced on every update. The person's layer (brand folder, preferences, working files, versions) is data the plugin reads. | An update never loses what a person built. See section 10. |
| S11 | **Skills are read-only in use.** A skill never edits plugin files and never changes the engine during a session. | Behaviour changes through the person's layer or through an issue and pull request here, never through a local edit an update would wipe. |
| S12 | **A repeated correction is recorded, not patched.** It becomes a rule, a preference or an upstream issue. | The kit learns from use the same way it learns from comments (section 7). |

## 3. Skills and agents

Three skills the person invokes. Everything beneath them is an agent or a stage file the skill reads
when it reaches that stage.

| Skill | Does |
|---|---|
| `brand` | Reads guidelines, templates and approved examples; drafts tokens, voice and rules, each with its source; asks the person to confirm only what was inferred rather than read; writes the brand folder. Wraps the engine's existing `brand` commands. |
| `create` | Survey or resume; name the document type; gather facts with sources; agree the outline (the one stop); draft through agents; build; look at every page and fix what was found, at most two rounds; give the person the PDF, the editable copy and the look summary line. |
| `review` | Read a review copy; compare it with the version it was built from by section; apply wording; classify comments; ask once for the structural items; redraft; rebuild through the same look; propose rules from lasting preferences; give the person the next version with its look summary line. |

| Step | Who | Why |
|---|---|---|
| Survey, name the type, ask the questions, agree the outline | the `create` skill | judgement and conversation |
| Gather facts with source keys | `gather` agent | bounded extraction with a fixed output shape |
| Write one section from its brief and facts | `write-section` agents, one per section, in parallel | a tight brief and a checkable output |
| Assemble, validate, render, run checks, rasterise, version | `ai-docs-kit` commands | deterministic |
| Read the rendered pages and report what is wrong, by section | `look` agent | judging a picture is the quality gate |
| Route findings, at most two rounds | the skill | judgement over a bounded list |
| Classify review items and draft the edit a comment asks for | `review-classify` agent | bounded classification |
| Test a proposed rule against the example and the approved exemplars | `ai-docs-kit rule` | a learning must fail first |

An agent gets everything it needs in its prompt and never explores the repository. Its output is
validated by an `ai-docs-kit` command before the skill reads it.

After the outline is agreed and its working file has a source list, the skill saves the gathered
facts with `ai-docs-kit facts add <name>.md <facts.json>`. The input is the gather agent's `facts`
array: each entry has `text`, `source` and an optional `locator`. The command refuses an unlisted
source key before saving anything and keeps each text, source and locator combination once.
Every figure is compared with the source text using the fact guard's tokeniser:
the cited PDF page, transcript cue or table cell or row; plain text, Markdown
and facts without a locator use the whole file. Local paths resolve relative to
the working file. Unsupported figures and unreadable local sources refuse the
whole batch, with one stderr line per refused fact and no store change. A URL
fact is accepted with a persistent `unverified` mark and a warning because the
engine cannot read its source text.

A derived figure absent from its source is refused as a plain fact. Store a
`calc:` line instead, such as `calc: ratio(184000, 61300) = 3.00`, after the
facts supplying its operands. The existing calculation guard checks operands
against earlier stored or same-batch facts and recomputes the result. Drafts
cite those operand facts beside the figure and repeat the calculation in the
section's note. Supported operations are sum, difference, ratio and percentage.
`ai-docs-kit facts list <name>.md` prints one fact per line with its key and locator. `section put`
uses every stored fact as evidence alongside the sources, front matter and section's previous text;
unsupported figures, dates, names and source keys are still refused. A missing fact store contributes
no extra evidence.

The guard excludes inline citation metadata such as `[S3 p.6-7]`, `[S1, p. 12]` or `[S1 00:41]` from claim and
evidence tokens, and validates the source key in both prose and bullets. A page or timestamp cannot
support a number in a claim, including when the citation appears in the section's previous text.
The working file keeps the citation text unchanged.

Ordinary opening words such as `The` and `In` are excluded from capitalised names at sentence
boundaries, including after closing quotation marks or parentheses. The remaining name, including a single word
such as `EU` or `Varnholm`, still needs evidence. A month on its own is calendar wording; the guard
still checks the year and numeric day.
Evidence retains isolated capitalised words even at sentence openings, so a gathered fact beginning
with a name can support that name after an opening word in a draft.
Source keys and source text are tokenised as separate evidence entries, so a capitalised opening
such as `The EU` or `The Northern Fisheries Council` keeps the same sentence boundary as the draft.
Text after a bold head ending in a colon or full stop, inside or just outside the closing bold
markers, also starts a sentence. This includes `**Option A: Extend as proposed.**` and
`**Eastfield:** Keep the zone`, in prose and list items; longer names still need evidence.
Parsed item heads retain sentence-start normalisation: `Summary:` is ordinary opening wording
and `In March:` is calendar wording; a remaining name such as `Varnholm` in `In Varnholm:`
still needs evidence.
`section put` accepts a number word immediately before `source`, `sources`, `section` or `sections`
when it equals the working file's corresponding count. This exemption belongs only to that phrase;
the count supplies no evidence for an unrelated figure, including in a later replacement.

The voice text from `section brief` explains that source quotations keep their own wording,
including contractions such as "don't know" even when the brand avoids them. The banned-term
check exempts a complete quotation in straight or curly quotation marks only when its wording
appears in a listed source entry or gathered fact. Unquoted terms and unsupported quotations
still produce findings. `section put` warns on stderr once for each capacity limit exceeded by
the replacement's chosen component, using the same measures as the build. Capacity warnings
still save the block and exit 0; the existing patch guards decide refusals.

Working-file patches hold an advisory lock on the shared `.ai_docs_kit` folder across
reading, checking and writing, without creating a lock file. `section put` also prepares
its evidence inside this lock. Its optional `--base-rev N` refuses a changed revision
with exit 1 and `document is at rev M, not N; read it again`, leaving the working file
and oplog unchanged. Without the option it reads the current revision inside the lock.
Writing requires `fcntl`, available on macOS and Linux; other platforms refuse clearly.

`ai-docs-kit undo <name>.md` applies the last edit's recorded inverse as a new
human-authored patch; `redo` reapplies the most recently undone edit. Both print
the new revision. Repeated undo walks backwards through that working file's
edits, skipping undo and redo entries. An edit without a recorded inverse stops
the walk, and a new edit to that file clears its redo history. Empty history
and a missing inverse exit 1 with one stderr line. Manual edits after undo also
invalidate redo, including changes to another section or to formatting; a
refused redo preserves the working file and oplog byte for byte. History stays append-only,
and inverse operations preserve unrelated edits in the current working file.
The Python API offers `undo(path, base_rev)` and `redo(path, base_rev)`, returning
`HistoryResult` with `rev` and `target_rev`. They check the base revision and
select and apply the history patch within the same project lock as other edits.
Oplog entries identify history actions and their target revisions explicitly;
ordinary patch reasons never identify an undo or redo. File hashes before and
after each patch detect manual edits and prevent a discarded redo branch from
returning after later history operations.

Each new version keeps an independent, byte-for-byte copy of the working file
as `source.md`, outside the manifest's deliverable outputs. Builds capture these
bytes before parsing, so edits during rendering stay in the working file and
cannot change the version's source. Existing versions are never backfilled.
`ai-docs-kit restore <name>.md v3` restores its sections
as one human-authored patch with reason `restore v3` and prints the new revision.
Undo recovers the pre-restore sections, including their order and ownership,
without losing earlier history. An unknown version or one without `source.md`
exits 2 with one stderr line naming the version. Front matter, context and
sources cannot be patched, so a restore changing any of them is refused before
writing. Both files must have unique section ids for unambiguous patch targets.
The Python API's `restore(path, version, base_rev)` returns the restored
`Document` and checks and applies the patch under the same project lock.

The skills ship as a Claude Code plugin from this repository: `.claude-plugin/plugin.json`, a
marketplace manifest, `skills/<name>/SKILL.md` and `agents/<name>.md`. Skills call the engine through
`${CLAUDE_PLUGIN_ROOT}/bin/ai-docs-kit`, which runs the package with `uv` from the plugin folder.

## 4. The build

`ai-docs-kit theme which <name>.md` prints the theme folder and the rule that selected it;
`--json` prints an object with `path` and `rule`. The shared engine function `resolve_theme(path)`
resolves front matter `theme` first as a folder relative to the working file (identified by
`theme.yaml`), then as a brand slug in `.brand/<slug>/theme` beside that file, then as `neutral`.
An absolute theme folder is also accepted, including a brand kept elsewhere with `--root`.
Without a theme key, exactly one brand selects that brand's theme, and no brand selects the shipped
neutral theme. An unknown value or a missing key with two or more brands is refused with exit 2
and one stderr line naming the candidates. Brand discovery uses the brand workspace's slug and
repository checks, independent of the caller's current folder. Theme loading still validates the
selected folder's tokens, fonts and voice.

`build` and `check` use this same resolution when `--theme` is omitted. An explicit `--theme <folder>`
wins even if the working file's selection would be refused. Projects with a single brand and no
theme key therefore build and check with that brand's theme. The create and review skills call
`theme which` for their working file and pass its result to commands that need an explicit theme.

`ai-docs-kit build <name>.md` does, every time:

1. parse and validate the working file (source checks);
2. compose and render the PDF with Typst;
3. write the Word copy for a document, read layout facts and run the geometry and pixel checks;
4. rasterise every page into the version's `pages/` folder, with `pages.json` (which sections sit on
   which page) and a contact sheet (deck) or spreads (document);
5. write the PowerPoint copy for slides;
6. write a new version under `<name>.versions/vN/` with the engine's findings and replace
   `build/<name>.findings.json` with the same findings, including an empty array for a clean build
   (`--out` selects another build folder).

After the look, source findings acquire their section's starting page from layout marks.
`look --pages` names that page, or the section when an older finding has no page.

Documents with a front matter title open with a title block above the first section
on page 1, without a separate cover page. It shows the title, the audience when
present and the build date in British form. The theme draws it using document
type and colour tokens. Title and audience have `front.title` and `front.audience`
element marks, named by `look --pages`, outside the document's sections. The
page index lists only editable section ids. Section font-size findings exclude
the title block, whose marks and field paths remain in the page's regions and
layout facts. The composition stores the date and optional front matter for that
version; older compositions without them remain readable. Untitled documents, slides and
component swatches have no title block.

Document builds support `body`, `callout`, `chart`, `bullets` and `key-numbers`.
Document charts draw bar, column and explicitly requested `type: line` data resolved by `render/chart_spec.py`,
using the document's available width and the slide chart's marks and field paths.
The `doc-chart` component holds up to 24 categories and five series; unsupported
data stays in `chart-table`. Both components retain the resolved twin table.
Lines join values in category order, with one marked point per value and the theme's
categorical colours. The automatic chooser and slides still draw bars and columns only.
`check --outline` defers a missing-data `source.intent-known` finding when the
intent has a component for the format once data is present. Unknown intents
still fail, and full checks and builds still report missing chart data.
The document list draws headed or plain items, nested sub-lines and citations;
key figures draw 2 to 4 values with labels in the document's type scale. Both
write their items as lists inside the section's bookmark in the Word copy.
All document components draw their paragraphs too. The section records the order of
paragraphs, list items and chart data as field paths, so the PDF and Word copy
retain the working file's reading order, including prose after a list. A chart's
numbered Word reference sits where its data appears. Callout prose stays inside
the unbreakable frame. Key-number prose flows outside the unbreakable strip;
prose between figure lists separates them into strips.
Generated chart references in the Word copy have a reference style that inherits
the body appearance. Review plans exclude these references from editable prose
and retain their data position, including after paragraph insertions or deletions
and reference moves. An edited generated reference is reported as unplaced text.
The reference's stored position and text alignment identify its occurrence even
when it loses its style or inserted prose inherits that style. Style hints are
used only for an edited reference within its aligned replacement span. Literal
body prose with the same wording remains editable, including in older copies.

Document builds run `geo.text-present` against every section heading, paragraph
and list item, including its head, body and sub-lines. Each block must appear
in the PDF text from the layout facts and in the Word copy. Matching ignores
line breaks, line-end hyphenation, runs of whitespace and citation markers.
Each missing block is an error naming the section, field path and opening
words; a Word loss says `Word copy` and is separate from a PDF loss. Both
outputs contribute to the same version's findings and look record. Ordinary
builds still finish with open errors; `check` exits 1 and `build --final` reports
the version as not ready. `check` reads an existing Word copy in the output
folder without replacing it; without a copy it checks the PDF alone. Slides
and the document's front matter title block are outside this rule's scope.

The `look` agent then reads `pages/` and returns findings as JSON. `ai-docs-kit look <version>
--findings <file>` validates them (sections and pages exist, severities known) and adds them to the
version's look record. The skill fixes what was found and rebuilds, at most twice, then reports what
remains by section.

The ship gate requires the version's look record to carry the look agent's findings. Recording
an empty array through `look --findings` counts as read; a missing agent findings list does not.
The engine page pass stays in the same look record with its existing fields and is reported as
`engine page pass`, including any pages it could not check. A clean `build --final` without agent
findings still writes its version, then exits 1 with `not ready: not looked at by the look agent`.

The skill gives the person the PDF, the editable copy and the summary line of `look`, which names any
open error and any page the engine page pass could not check. Missing look agent findings must also
be reported before the version can be described as ready to ship.

## 5. The editable copies

Both copies carry the section id on everything they hold, so a review copy maps back to the working file.

### 5.1 PowerPoint

One slide per PDF page. Each slide is built from the layout facts of that page:

* a full-slide picture of the page rendered with its text hidden (the same Typst build with text drawn
  transparent, so layout is identical);
* one native text box per text field, at the field's measured box, in the theme's font, size and
  colour, named `<section-id>/<field-path>`;
* tables as native tables where the component is a table, named the same way;
* speaker notes from the section's notes field, when it has one.

A textless slide carries its section id in its slide name, so deleting or moving an image-only
section still produces a structural confirm item. Named text boxes remain the primary section anchor.

The text-hidden render guarantees the picture and the boxes line up; the field boxes come from the
same layout facts the checks read. A reviewer who retypes a bullet edits one named text box.

### 5.2 Word

Headings, paragraphs and lists, in section order. Each section sits inside a bookmark named by its
id. Word accepts only names of at most 40 letters, digits and `_` that start with a letter, so
`bookmark_names.py` keeps a valid id as it is, writes any other id as `Xenc_` plus an escape (`__` for
`_`, `_x<hex>_` for another character) and, when that runs past 40 characters, as `Xh_` plus a hash of
the id. The copy stores the map from each `Xh_` name to its id in its custom document properties, so
a copy that travels alone still reads back; `review read` reports text under an `Xh_` name missing
from the map as `unplaced`. A table, chart or figure becomes one line: `[Table 2: <title>]`. Fonts and colours come from the
theme's tokens; nothing else is styled.

## 6. The review round trip

`ai-docs-kit review read <review-copy>` finds the working file and the version the copy came
from, reads it, and writes a review plan.

| The reviewer did | Detected by | Becomes |
|---|---|---|
| Rewrote text inside a section | bookmark (Word) or shape name (PowerPoint); diff against the copy it was built from | The wording is applied; the section's text becomes `owner="human"` |
| Left a comment | comment anchor mapped to a section | A confirm item; the agent proposes `apply` (the comment is the wording), `redraft` (an ask) or `restructure` |
| Deleted a slide or a section | section id missing | A structural confirm item |
| Reordered | id sequence differs | A structural confirm item |
| Added text with no section id | unmapped text | A confirm item for the person to place |
| Bolded, recoloured, moved or resized | run properties, geometry | An emphasis hint, never applied |

Word comments come from the document's internal comments relationship target with their ranges,
falling back to `word/comments.xml` when no internal comments relationship is present;
tracked changes come from `w:ins` and `w:del`.
The plan keeps a section's edited heading in `title` and its body in `wording`, each null when
unchanged. Headings are identified by the Word paragraph's heading style, so a body paragraph that
repeats the title stays in the body. An unchanged trailing source line is excluded from body wording
using the composition stored with the copy's version; identical body paragraphs are kept.
The source still counts as section content: clearing a heading-free section's body while retaining
its source applies empty body wording rather than proposing to delete the section.
A section still present with its title cleared is refused with
exit 2 before a plan is written, including when the section holds only a title. Removing the whole
section remains a structural confirm item. Plans written before the split lack the `title` key and
keep the previous wording path when applied.
Bookmarks move when Word saves, so a change is attributed by range overlap. A Word copy with nothing
in it raises a warning that tracked changes may have been off. PowerPoint comments come from both the
legacy (`ppt/comments/`) and the modern (`ppt/comments/modernComment_*`) parts, anchored to a slide
and, when given, a shape.

`ai-docs-kit review apply <name>.md --plan <decided.json>` applies wording, writes `redraft=` asks,
applies the structural items the person accepted, and prints what it touched. It refuses when the
working file changed since the version the copy came from in a section the plan touches, and says which. It also reports sections that changed since then or went missing.

A section with `owner="human"` is never rewritten by an agent. A redrafted section stays agent-owned
and carries `because="redrafted for <who> at v<N>: <the ask>"`.

## 7. Learning from comments

When a comment states a lasting preference, the `review` skill proposes a rule in the engine's rule
format, with the comment as its provenance. `ai-docs-kit rule test <rule> --example <version>/<section>`
accepts it only if it fires on the commented section and on none of the brand's approved exemplars.
The version folder is identified by its `composition.json`; the complete section id after it is
kept literally, including `./` and leading or trailing slashes. An accepted rule enters the brand's
rulebook on probation (advisory) and blocks only after the person promotes it. This is principle 8 of
`docs/ENGINE.md` applied to comments.

## 8. What appears in a project folder

```
<folder>/
  <source material the person dropped in>
  <name>.md                 the working file: front matter, sources and sections
  .ai_docs_kit/facts/<name>.md.json  gathered facts agreed at the outline
  <name>.pdf                the latest deliverable
  <name>.pptx | <name>.docx the latest editable copy
  <name>.versions/vN/       every build: source.md, PDF, editable copy, pages/, manifest with the look record
```

Caches and the render kit live under the plugin's data folder, never in the project folder.
The gathered facts are the person's data, not a cache: keep `.ai_docs_kit/` beside the working file
when moving it to another folder.

## 9. Not in scope

* A web interface, a browser editor, hosted collaboration, accounts.
* Exporting the deliverable as Office files. The editable copy is a review surface.
* A model call made by the engine or by a skill outside the session's Claude.

## 10. What the person owns and what the plugin owns

People build their own brand, rules and habits by using the skills. None of that may live in the
plugin, because Claude Code replaces the plugin's files on every update.

### 10.1 The plugin's layer

The engine package and its command, the three skills, their agents, the component library, the
neutral theme and the engine's own rule catalogue. It is installed into Claude Code's plugin folder,
versioned, and replaced as a whole on update. It is read-only in use: no skill or agent writes there,
and a session never changes engine code. A new capability (an output, a component, a rule kind)
reaches the engine as an issue and a pull request on this repository, built and tested like any other.

### 10.2 The person's layer

Everything the person grows lives in their project folder and is theirs:

* the brand folder, `.brand/<slug>/` by default (the `brand` skill's `--root` points elsewhere): the
  materials, the theme (tokens, voice, rules, each with its source), the rulebook with the rules
  learned from comments, and later the brand's own components;
* `preferences.md` in the brand folder: how the person wants the skills to work, in their own words
  and dated;
* the working files and versions of section 8.

A brand belongs to a project folder by default. A person who uses one brand across many projects keeps
it in one place and points each project at it with `--root`.

### 10.3 Changing behaviour without editing the plugin

The skills read the brand's rulebook and `preferences.md` before their first step. When a person
corrects the same behaviour twice, the skill offers to record it in one of three places:

| The correction is... | Example | Recorded as |
|---|---|---|
| checkable on the page or the source | "never say 'leverage'", "charts start at zero" | a rule, through the rule flow of section 7, on probation |
| a way of working | "ask me before redrafting the summary" | a dated line in `preferences.md` |
| an improvement for everyone | a missing check, a better outline step | an issue on this repository, drafted for the person to send |

A person may still write their own skill. Plugin skills are namespaced, so theirs sits beside ours
under its own name instead of replacing it. That is supported but carries no guarantee across updates.

### 10.4 Updates

An update replaces the plugin's layer and never writes in the person's layer, with one exception: a
format migration the person runs. The brand folder records its format version; the engine reads the
current version and the one before; `ai-docs-kit doctor` reports an older folder and names the command
that upgrades it, and the upgrade keeps a copy of what it replaced and writes an entry to the brand's
log.

