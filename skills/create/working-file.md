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

A `doc` chart needs a `data` block for a full check or build. `check --outline`
accepts its intent before data exists; keep drafting the data after agreement.
Document bar, column and explicitly requested `type: line` charts draw as charts;
unsupported types use a table. Slides draw bar and column charts only.
Slide charts and tables use their data
components when data is present; some slide intents also depend on item count
or an image. The chooser handles those choices; do not guess a component from
the intent's spelling.

## Chart data

The published input definition is
[`docs/schemas/chart/ChartData.schema.json`](../../docs/schemas/chart/ChartData.schema.json).
Put a YAML mapping inside a fenced `data` block in a section with `intent="chart"`.
These fields describe its content:

| Field | Meaning |
| --- | --- |
| `type` | Optional requested chart type: `bar` draws horizontal bars, `column` draws vertical columns, and `line` draws connected points in documents. Omit it or use null for automatic choice. `pie` is accepted as a table fallback, but is not drawn. Unknown types fail schema validation. |
| `categories` | Required list of string labels, in display order. Quote numeric labels such as years. |
| `series` | Required list of series, each a mapping with `name` and `values`. |
| `name` | Series label for the legend and the table heading; defaults to an empty string. |
| `values` | Required list of finite numeric values in the same order as the categories. Supply one value per category. Negative values are allowed; strings, booleans and null are not numbers. |
| `unit` | Optional string applied to value labels. `GBP`, `USD` and `EUR` use currency symbols, `%` adds a percent sign, and other units follow the number. Omit it or use null for no unit. Keep unit text out of `values`. |
| `category_label` | Optional heading for the table's category column; defaults to an empty string. |
| `time_series` | Optional boolean, default false. True declares a time series and selects columns when `type` is omitted. |
| `ordered` | Optional boolean, default false. True declares ordered categories and selects columns when `type` is omitted. |

Without a requested type, the engine applies these rules in order:

1. `time_series: true` selects `column`.
2. `ordered: true` selects `column`.
3. Any negative value selects `bar`.
4. Two or more time-like categories, all recognised as years, quarters, months
   or ISO dates, select `column`.
5. Seven (7) or more categories select `bar`.
6. Other categories select `bar`.

An explicit drawn type takes precedence over these rules; automatic choice
never selects `line`. Documents draw `bar`, `column` and `line`. Slides draw
`bar` and `column`. A type the target cannot draw uses a table fallback with a
visible notice, the same categories, series names and formatted values.
Malformed data resolves as unsupported rather than being drawn; supply complete
numeric series instead of relying on the engine's recovery of older blocks.

For a worked document chart, add this section to the `format: doc` working file
above. The values are synthetic example data; replace them with gathered facts
and cite their source before using the chart in a report.

````markdown
::: {#d0f64 .section intent="chart" section="content" because="Compare the monthly trip counts"}
## Monthly trips by zone

```data
type: line
categories: [Jan, Feb, Mar]
series:
  - name: Upland
    values: [12, 18, 24]
  - name: Lowland
    values: [18, 24, 30]
unit: trips
category_label: Month
time_series: true
ordered: true
```
> source: Synthetic survey records
:::
````

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

Every figure must occur in the source text at its locator, using the guard's
normalisation (`1,200` matches `1200`, and `four` matches `4`). For PDFs cite a
page (`p.4`), for transcripts a cue (`00:41`), and for tables a cell
(`routes!B2`) or row (`routes!2`). Without a locator the whole source is checked;
plain text and Markdown always use the whole file. Locator metadata cannot
supply a figure. Source paths resolve relative to the working file's folder.
Missing or unreadable local sources are refused. URL sources are accepted as
`unverified` with a warning, because their text cannot be checked.

`facts add` refuses a derived figure stored as a plain fact when the source does
not state it. Store a `calc:` line instead, after the facts it uses. Each operand
must occur in an earlier stored or same-batch fact. Supported operations are
`sum`, `difference`, `ratio` and `percentage`; results are recomputed and rounded
to the stated decimal places. Use ungrouped operands, separated by commas;
`percentage` results end in `%`.

For example, the cost fact cites `[S1 p.4]`, the trips fact cites `[S2 00:41]`,
and their ratio is stored as:

```json
[
  {"text": "The service cost £184,000.", "source": "S1", "locator": "p.4"},
  {"text": "The service ran 61,300 trips.", "source": "S2", "locator": "00:41"},
  {"text": "calc: ratio(184000, 61300) = 3.00", "source": "S1"}
]
```

Show the figure with both operand citations and put the same calculation in its
section's private note. Keep the `calc:` line alone in that note so it matches
the guard's grammar:

```markdown
The cost per trip was £3.00. [S1 p.4] [S2 00:41]
> note: calc: ratio(184000, 61300) = 3.00
```

An incorrect result, missing operand or unsupported plain figure refuses the
whole batch with one stderr line per refused fact, leaving stored facts intact.

Write the working file directly only to lay down the agreed outline. Afterwards
read sections with `ai-docs-kit section get <name>.md <id>` and replace them only
through `ai-docs-kit section put <name>.md <id> --from <block file>`. Give each
agent the relevant syntax from this reference, its existing section and its
agreed facts so it never needs to explore the repository.
