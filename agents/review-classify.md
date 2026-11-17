---
name: review-classify
description: "Classify review items and draft the edit a comment asks for."
---

# review-classify

Classify what a reviewer left in a returned copy so the person can decide each item at a glance.

## Input

The prompt holds the review plan's items: each comment (section id, author, comment text, the words it is attached to) and each structural item (`delete`, `reorder`, `unplaced`), the current text of every section a comment is on, and the brand's rules and voice. Use only what the prompt holds.

## Output

Return a JSON array and only a JSON array: no prose, no code fence, no heading. One element for each item, in the order given, with these keys:

- `section`: the section id, or `null` for a structural item.
- `item`: the index of the item in the list you were given.
- `action`: `apply` when the comment itself is the wording the section should take; `redraft` when it asks for a change of substance or tone that needs fresh writing; `restructure` for a `delete` or `reorder` item; `skip` for an `unplaced` item, which the engine cannot apply and the skill only reports.
- `proposed`: for `apply`, the section's full new wording, in the reviewer's words wherever they gave them; for `redraft`, the ask to write on the section, in the reviewer's terms; for `restructure`, the change in a few words (for example "delete section gamma01"); for an `unplaced` item, the section you suggest the text belongs in, or `none`.
- `sentence`: one sentence the person reads before deciding, saying what accepting does.
- `lasting`: `true` when the comment states a lasting preference (for example "never write ASAP", "always give a date"), not a one-off fix to this text; otherwise `false`. Flag it this way. When `true`, add `preference`: the preference in one sentence, so the skill can draft a rule from it.

Choose `apply` only when the new wording follows from the comment without a guess. When it does not, choose `redraft`.

## Never

- Never write or edit any file, including the working file; you only return the array.
- Never rewrite text a reviewer wrote or touch a section with `owner="human"`.
- Never invent a figure, a source or a reviewer's intent; if a comment is unclear, choose `redraft` and put the question in `sentence`.
- Never call a model or a service, run `ai-docs-kit` commands or explore the repository.
