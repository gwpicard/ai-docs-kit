---
name: write-section
description: "Write one section from its brief and facts."
---

# write-section

Write one section of a working file.

## Input

The prompt holds the working file path, one section id, its agreed brief, its intent, the facts it may use (each with a source key) and the output of `ai-docs-kit section brief` for this section and theme. The section brief supplies the format's voice summary, banned and preferred terms, chosen component and capacity limits. Follow these rules and limits when writing. Read the section as it stands with `ai-docs-kit section get <file> <id>`. A redraft ask or a finding in the prompt says what to change.

Wording quoted from a source keeps its own form, including contractions such as "don't know", even where the brand's voice avoids them. Keep quotation marks and the source key; the complete quoted wording must appear in a listed source or its gathered facts. Banned terms outside a supported quotation still need replacing.

## Output

Return one section block and nothing else, in the working file's own form: a fence `::: {#<id> .section intent="<intent>" ...}`, a heading, the text and a closing `:::`. Keep the id, the intent and any attribute you were not asked to change. Every claim carries its source key as `[S1 00:41]`. The caller saves the block with `ai-docs-kit section put <file> <id> --from <block file>`; you may do so yourself only when the prompt says to, and only with that command.

## Never

- Never write or edit the working file directly; the only way in is `ai-docs-kit section put`.
- Never use a fact the prompt does not give you, or a source key it does not list. Never invent a number.
- Never touch another section, and never rewrite a section whose owner is `human`.
- Never apply formatting for effect, add an em dash or leave the brand's voice rules.
- Never explore the repository or call a model or a service.
