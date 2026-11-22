# Working-file reference

Read this when laying down an outline or briefing a `write-section` agent. It is
the authoring reference; no engine source reading is needed. The working file is
UTF-8 Markdown named `<name>.md`. It holds meaning and content; the theme and
chooser supply appearance.

## Front matter, sources and sections

Start with YAML front matter between `---` lines. Set `doctype` (`report` for a
document, `pitch-deck` for a deck), `format` (`doc` or `slides`), `title`,
`audience`, `purpose`, `theme` (a theme name or path) and `locale: en-GB`.
Include any keys the document type requires. The format must match the type.
Optional `## Context` holds the agreed brief and is never rendered.

This document example shows the source list and section syntax:

```markdown
---
doctype: report
format: doc
title: Trial findings
audience: The trial team
purpose: Agree the next step
theme: neutral
locale: en-GB
---

## Context

Report what the trial established and what remains open.

## Sources

- [S1] trial-notes.pdf, trial observations
- [S2] workshop.vtt, discussion transcript

::: {#a7c31 .section intent="body" section="introduction" because="Introduce the trial and its scope"}
## Trial scope

The trial tested the collection process. [S1 p.4]
:::

::: {#b8d42 .section intent="body" section="content" because="Explain what the team observed"}
## Collection process

The team collected the readings before the workshop. [S1 p.4]
:::

::: {#c9e53 .section intent="callout" section="findings" because="State the finding supported by the workshop"}
## A further check is needed

- **Next step:** The team asked for a further check. [S2 00:41]
:::
```

List each source under `## Sources` as `- [S1] <file or URL>, <description>`.
Use unique, stable keys consisting of letters followed by digits, such as `S1`
and `S2`. A citation names one of those keys: `[S1]`, `[S1 p.4]` or
`[S2 00:41]`. Put it beside the claim, in prose or a bullet. Every number and
claim must trace to a source fact. A locator identifies a page, timestamp or
other place in the source; it is metadata, never evidence for a claim's number.
Write `[GAP: the missing fact]` when the material does not answer something.

Each section opens with `::: {#<id> .section intent="<intent>" ...}` and closes
with `:::` on its own line. Give every section a unique, stable id after `#`,
without spaces. Prefer five lower-case hexadecimal characters (`a7c31`), the
engine's generated form. Keep an existing id when wording or order changes;
never reuse a deleted section's id. `section="introduction"` names the outline
line in the document type; `intent="body"` names the content's form.

The first `## Heading` inside a section is its title. Write prose as paragraphs,
items as `- text`, and an optional item head as `- **Head:** text`. Indented
bullets are subitems. `> note: ...` is a private presenter or author note;
`> spoken: ...` is the takeaway; `> source: ...` is a figure's source line.
A fenced block tagged `data` holds a YAML mapping for a chart or table; its keys
must fit that component's data schema. Other fenced blocks hold code.

## Briefs, overrides and redrafts

Attributes belong in the opening fence, as `name="value"`. Double-quote any
multiword value, including `because=` and `redraft=`. Rephrase embedded double
quotes rather than nesting them.

- `because="Explain the finding from the trial"` records the section's brief or
  the reason for a change. It is metadata, never body text.
- The chooser picks the component from the intent and content. An explicit
  `component="..."` override requires a reason in `because="..."`.
- `redraft="Explain the next step more clearly"` records a pending ask, never
  wording to paste. Draft from the agreed facts, then save through
  `ai-docs-kit section put <name>.md <id> --from <block file> --redraft-done`.
  That clears the ask and supplies `because="redrafted: <the ask>"` if the
  replacement has no reason. Keep the section's id and other attributes.
- `owner="human"`, `lock="text"` and `lock="all"` protect a section from agent
  replacement. Leave it unchanged and report the refusal.

Never add appearance attributes such as `color=`, `font=`, `size=`, `x=` or `y=`.

## Allowed intents by format

This table is checked against `src/ai_docs_kit/render/chooser.yaml` by
`tests/test_create_working_file_reference.py`. Use only an intent listed for the
working file's format. Intent names and component names are distinct.

| Format | Allowed intents |
| --- | --- |
| slides | `cover`, `quote`, `statement`, `bullets`, `agenda`, `comparison`, `key-numbers`, `table`, `chronology`, `people`, `contact`, `chapter-break`, `image-text`, `card-set`, `full-image`, `chart`, `closing`, `process`, `matrix` |
| doc | `body`, `callout`, `chart`, `bullets`, `key-numbers` |

A `doc` chart needs a `data` block. Slide charts and tables use their data
components when data is present; some slide intents also depend on item count
or an image. The chooser handles those choices; do not guess a component from
the intent's spelling.

## Store the facts before drafting

After the outline is agreed and its source list exists, save the gather agent's
`facts` array to `<facts.json>`. Each entry has `text`, `source` and an optional
`locator`, for example:

```json
[{"text": "The team asked for a further check.", "source": "S2", "locator": "00:41"}]
```

Run `ai-docs-kit facts add <name>.md <facts.json>`, then
`ai-docs-kit facts list <name>.md`. Every source key must already be listed in
the working file. Repeated additions keep each text, source and locator
combination once. Facts live in `.ai_docs_kit/facts/<name>.md.json` beside the
working file; keep both when moving the document.

Write the working file directly only to lay down the agreed outline. Afterwards
read sections with `ai-docs-kit section get <name>.md <id>` and replace them only
through `ai-docs-kit section put <name>.md <id> --from <block file>`. Give each
agent the relevant syntax from this reference, its existing section and its
agreed facts so it never needs to explore the repository.
