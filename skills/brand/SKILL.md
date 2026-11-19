---
name: brand
description: "Read brand guidelines and write the brand folder: tokens, voice and rules, each with its source."
---

# brand

Build the brand that `create` and `review` use, from the person's guidelines, templates and approved examples. The result is a theme folder that `ai-docs-kit build --theme <dir>` accepts.

Run every command as `${CLAUDE_PLUGIN_ROOT}/bin/ai-docs-kit`. Commands take the brand's slug and, optionally, `--root <dir>`; without it, brands live in `.brand/<slug>/` under the current folder. Check the installation first with `ai-docs-kit doctor`.

## Preferences

Before the first step, read `preferences.md` (in `.brand/<slug>/`, or under `--root`): its `## All skills` section and its `## brand` section. Follow both, together with the brand's rulebook.

Say once, early, that this skill records preferences rather than being edited: the person's corrections go into their brand folder, which an update leaves alone.

When the person corrects the same behaviour twice, offer one of three records:

- A rule, through the rule flow (`ai-docs-kit rule test`, then `ai-docs-kit rule adopt` on their yes).
- A line `- YYYY-MM-DD: <the person's words>` under `## All skills` or under `## brand` in `preferences.md`, written by you directly.
- An upstream issue, for a change that would help everyone. Show the person the title and body first. Run `gh issue create --repo gwpicard/ai-docs-kit` only on their yes. If `gh` is missing or not signed in, show the text and the new-issue link (`https://github.com/gwpicard/ai-docs-kit/issues/new`) instead. Describe the behaviour in general terms: the body holds no brand material, document text, names or file contents from the person's project.

Never edit a plugin file.

## Rules

- Never invent a value the material does not hold. A token, a term or a rule comes from a page, a template or a measurement, and keeps its source. If the material is silent, leave the value unset and let the engine list it as a gap.
- Every value carries a label: Measured, Derived, Inferred or Answered. Ask the person to confirm only values labelled Inferred, and record the confirmation with `ai-docs-kit brand answer <slug> <question-id> (--option <id> | --text <answer>)`. Do not ask about Measured or Derived values, and do not reopen an Answered one.
- A value measured from a template the brand supplied may make a hard rule. A value measured only from examples makes a proposed rule.
- Brand material never enters the repository. Keep it under the brand folder (`.brand/` is git-ignored), never commit fonts, logos, guidelines or examples, and never copy their content into a test, a comment or a message.
- Make no model call of your own beyond your own reading. Do not set `DOCLA_LIVE` and do not run the commands that call a model on their own (`segment`, `extract`, `tie`, `calibrate`).

## Steps

1. Create the folder: `ai-docs-kit brand init <slug>`. Ask the person to put guidelines, templates (`.pptx`), approved examples (PDF), logos, fonts and notes into the matching `materials/` subfolders. Fonts come from the person, with a `fonts.yaml` naming each file, its family, weight and licence.
2. Intake: `ai-docs-kit brand intake <slug>` records what was supplied. Then run `ai-docs-kit brand fonts <slug>`, `ai-docs-kit brand templates <slug>` and `ai-docs-kit brand parse <slug>`, and `ai-docs-kit brand gaps <slug>` to list what is missing. Tell the person which materials are missing and what each gap leaves unknown.
3. Measure: `ai-docs-kit brand measure <slug>` measures the approved example pages. Then `ai-docs-kit brand reconcile <slug>` compares the sources; agreements settle values, conflicts become questions.
4. Synthesise: `ai-docs-kit brand synthesise <slug>` writes tokens, voice and rules into `theme/`, each with its source and label. Read `theme/tokens.yaml` and the guideline pages yourself to check that every value traces to its source.
5. Questions: read `theme/ingest/questions.yaml`. Ask the person each open question once, with the quote or page it came from. Record the answer with `ai-docs-kit brand set <slug> <token.path> <value> --reason "<why>"`. If the answer departs from the brand's own sources, the command refuses; repeat it with `--approve` only when the person has said so.
6. Specimen check: `ai-docs-kit brand specimen <slug>` renders the specimen pages from the new theme. Look at every page. Report anything that departs from the examples (wrong font, colour, margin, overflow) and fix it through a question or a `brand set`, then render again.
7. Finish: build a sample to prove the folder works with `ai-docs-kit build <file> --theme .brand/<slug>/theme`. Tell the person the theme path, which values are still Inferred and unconfirmed, and which gaps remain. `ai-docs-kit brand log <slug>` lists every change with its reason.
