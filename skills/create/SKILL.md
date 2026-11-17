---
name: create
description: "Write a branded report or deck as PDF from agreed facts and an agreed outline, then look at every page."
---

# create

Turn what the person needs into a looked-at PDF and its editable copy (Word for a document, PowerPoint for a deck). Run every command as `${CLAUDE_PLUGIN_ROOT}/bin/ai-docs-kit`. Check the installation first with `ai-docs-kit doctor`.

Before the first stage, read the brand's rulebook and `preferences.md` (in `.brand/<slug>/`, or under `--root`). Follow them. When the person corrects the same thing twice, offer to record it as a rule, a dated line in `preferences.md` or an upstream issue. Never edit a plugin file.

## Stages

The outline is the one stop. The person is asked once, at the outline, and every other stage runs without asking. Read each stage file when you reach it.

1. `survey.md`: find the project folder, resume an earlier working file or start a new one, and name the document type.
2. `gather.md`: collect facts with source keys from the material, through the `gather` agent.
3. `outline.md`: propose the outline and stop until the person agrees it. This is the one stop.
4. `draft.md`: write every section through `write-section` agents, in parallel, and build.
5. `look.md`: have the `look` agent read every page, fix what it found in at most two rounds, then report what remains by section.
6. `ship.md`: give the person the PDF and the editable copy, and mark the version sent only through `ai-docs-kit sent`.

## Rules

- The working file `<name>.md` is the whole state. Change a section only through `ai-docs-kit section put`. Write the file directly only to lay down structure the person agreed at the outline.
- Agents get everything they need in their prompt and never explore the repository. Validate their output with an `ai-docs-kit` command before relying on it.
- Make no model call of your own beyond your own reading, and set no API key.
- A number shown to the person traces to a source fact. Never invent a figure or a source key.
- Write in British English, with no em dashes.
