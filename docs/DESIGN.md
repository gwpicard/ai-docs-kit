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
| S7 | **No version reaches a person unlooked-at.** A version is marked sent only when its look record has no open error. | The same guarantee as the engine's ship gate, extended to the look agent. |
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
| `create` | Survey or resume; name the document type; gather facts with sources; agree the outline (the one stop); draft through agents; build; look at every page and fix what was found, at most two rounds; mark the version sent. |
| `review` | Read a review copy; compare it with the sent version by section; apply wording; classify comments; ask once for the structural items; redraft; rebuild through the same look; propose rules from lasting preferences; mark the next version sent. |

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

The skills ship as a Claude Code plugin from this repository: `.claude-plugin/plugin.json`, a
marketplace manifest, `skills/<name>/SKILL.md` and `agents/<name>.md`. Skills call the engine through
`${CLAUDE_PLUGIN_ROOT}/bin/ai-docs-kit`, which runs the package with `uv` from the plugin folder.

## 4. The build

`ai-docs-kit build <name>.md` does, every time:

1. parse and validate the working file (source checks);
2. compose and render the PDF with Typst;
3. read layout facts and run the geometry and pixel checks;
4. rasterise every page into the version's `pages/` folder, with `pages.json` (which sections sit on
   which page) and a contact sheet (deck) or spreads (document);
5. write the editable copy;
6. write a new version under `<name>.versions/vN/` with the engine's findings.

The `look` agent then reads `pages/` and returns findings as JSON. `ai-docs-kit look <version>
--findings <file>` validates them (sections and pages exist, severities known) and adds them to the
version's look record. The skill fixes what was found and rebuilds, at most twice, then reports what
remains by section.

`ai-docs-kit sent <version> --to <who>` refuses while the look record has an open error or a page that
was not looked at.

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

The text-hidden render guarantees the picture and the boxes line up; the field boxes come from the
same layout facts the checks read. A reviewer who retypes a bullet edits one named text box.

### 5.2 Word

Headings, paragraphs and lists, in section order. Each section sits inside a bookmark named by its
id. A table, chart or figure becomes one line: `[Table 2: <title>]`. Fonts and colours come from the
theme's tokens; nothing else is styled.

## 6. The review round trip

`ai-docs-kit review read <review-copy>` finds the working file and the sent version the copy came
from, reads it, and writes a review plan.

| The reviewer did | Detected by | Becomes |
|---|---|---|
| Rewrote text inside a section | bookmark (Word) or shape name (PowerPoint); diff against the sent copy | The wording is applied; the section's text becomes `owner="human"` |
| Left a comment | comment anchor mapped to a section | A confirm item; the agent proposes `apply` (the comment is the wording), `redraft` (an ask) or `restructure` |
| Deleted a slide or a section | section id missing | A structural confirm item |
| Reordered | id sequence differs | A structural confirm item |
| Added text with no section id | unmapped text | A confirm item for the person to place |
| Bolded, recoloured, moved or resized | run properties, geometry | An emphasis hint, never applied |

Word comments come from `comments.xml` with their ranges; tracked changes from `w:ins` and `w:del`.
Bookmarks move when Word saves, so a change is attributed by range overlap. A Word copy with nothing
in it raises a warning that tracked changes may have been off. PowerPoint comments come from both the
legacy (`ppt/comments/`) and the modern (`ppt/comments/modernComment_*`) parts, anchored to a slide
and, when given, a shape.

`ai-docs-kit review apply <name>.md --plan <decided.json>` applies wording, writes `redraft=` asks,
applies the structural items the person accepted, and prints what it touched. It refuses when the
working file changed since the sent version in a section the plan touches, and says which.

A section with `owner="human"` is never rewritten by an agent. A redrafted section stays agent-owned
and carries `because="redrafted for <who> at v<N>: <the ask>"`.

## 7. Learning from comments

When a comment states a lasting preference, the `review` skill proposes a rule in the engine's rule
format, with the comment as its provenance. `ai-docs-kit rule test <rule> --example <version>/<section>`
accepts it only if it fires on the commented section and on none of the brand's approved exemplars. An
accepted rule enters the brand's rulebook on probation (advisory) and blocks only after the person
promotes it. This is principle 8 of `docs/ENGINE.md` applied to comments.

## 8. What appears in a project folder

```
<folder>/
  <source material the person dropped in>
  <name>.md                 the working file: the whole state
  <name>.pdf                the latest deliverable
  <name>.pptx | <name>.docx the latest editable copy
  <name>.versions/vN/       every build: PDF, editable copy, pages/, manifest with the look record
```

Caches and the render kit live under the plugin's data folder, never in the project folder.

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

