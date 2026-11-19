---
name: review
description: "Take a returned Word or PowerPoint copy, apply what the reviewer wrote and asked for, and produce the next version for the person to read."
---

# review

A person drops a returned Word or PowerPoint copy in the project folder and gets the next version, rebuilt and checked page by page. Run every command as `${CLAUDE_PLUGIN_ROOT}/bin/ai-docs-kit`. Check the installation first with `ai-docs-kit doctor`.

## Preferences

Before the first step, read `preferences.md` (in `.brand/<slug>/`, or under `--root`): its `## All skills` section and its `## review` section. Follow both, together with the brand's rulebook.

Say once, early, that this skill records preferences rather than being edited: the person's corrections go into their brand folder, which an update leaves alone.

When the person corrects the same behaviour twice, offer one of three records:

- A rule, through the rule flow (`ai-docs-kit rule test`, then `ai-docs-kit rule adopt` on their yes).
- A line `- YYYY-MM-DD: <the person's words>` under `## All skills` or under `## review` in `preferences.md`, written by you directly.
- An upstream issue, for a change that would help everyone. Show the person the title and body first. Run `gh issue create --repo gwpicard/ai-docs-kit` only on their yes. If `gh` is missing or not signed in, show the text and the new-issue link (`https://github.com/gwpicard/ai-docs-kit/issues/new`) instead. Describe the behaviour in general terms: the body holds no brand material, document text, names or file contents from the person's project.

Never edit a plugin file.

## Rules

- Change the working file only through the apply and section commands below. Never edit or write the working file by hand.
- Text a reviewer wrote makes the section `owner="human"`: an agent never rewrites it. A comment becomes an ask for fresh writing and its words are never pasted; a section rewritten for an ask stays agent-owned.
- Formatting in the copy (bold, italic, colour, moves, resizing) is never applied. Report it as an emphasis hint.
- The person is asked once, in step 3, and every other step runs without asking. Make no model call of your own beyond your own reading, and set no API key.
- Write in British English, with no em dashes.

## Steps

1. Read the copy: `ai-docs-kit review read <copy>`. It finds the working file and the version it came from, compares them by section and writes a review plan (`review-plan.json`, in that version's folder). A refusal means the copy has no earlier version beside it, or the archive is unreadable: say so and stop. Read the plan's `warnings` (for example, tracked changes may have been off).
2. Show one screen: for each section with changes, one line with the section id and what changed (wording applied, comments, emphasis hints), then the structural items (deleted, reordered, unplaced). Keep it to what fits on one screen; count the rest.
3. Classify and ask once. Pass the `review-classify` agent every comment and structural item of the plan, with the section's current text and the brand's rules. Its answer fills `proposed`, `action` and a one-line reason for each item. Show the person the items in one list, each with the proposal and its reason, and ask once which to accept. Offer only comments and `delete` or `reorder` items for acceptance: an `unplaced` item is shown with the suggested placement but is only reported, never offered, and `review apply` cannot place it. Tell the person to put its words in the right section themselves. A decision is a plain yes or no per item; an item the person does not accept becomes `skip` and is reported as declined.
4. Apply: write the decisions into the plan (`accepted`, `action`, `proposal` or `ask`) and run `ai-docs-kit review apply <working file> --plan <decided.json>`. It applies wording, writes the asks, applies the accepted structural items and prints what it touched. The review copy is compared with the version it was built from. `review apply` prints a line for each section that changed since then (`changed since v<N>: <id> (...)`) and for each that went missing (`missing: <id>`); name those sections plainly in the report. It refuses when the working file changed since that version, in a section the plan touches: report which sections and stop.
5. Redraft: for each section that now carries a `redraft=` ask, write the new text through a `write-section` agent and `ai-docs-kit section put <file> <id> --from <block> --redraft-done`. Skip any section with `owner="human"`.
6. Rebuild and look: run `ai-docs-kit build <working file>`, then have the `look` agent read every page and fix what it finds in at most two rounds, as the `create` skill does. Record the findings with `ai-docs-kit look <version> --findings <file>`.
7. Report, in plain prose: any open error and any page not looked at (the summary line of `look --findings`), what was applied, what was redrafted, what was declined, what is unplaced, the emphasis hints (never applied) and any rule proposed. Give the paths of the new PDF and editable copy.

## Learning from comments

When the agent flags a comment that states a lasting preference, draft one rule in the engine's rule format (`origin: feedback`, `status: proposed`, a source-tier `check`, the comment as its provenance). For a correction in a bullet, use `field: items`; for paragraph text, use `field: paragraphs`. `rule test` sees the same text fields as `check`. Run `ai-docs-kit rule test <rule> --example <version>/<section> --theme <brand theme>`. It passes only if the rule fires on the commented section and on none of the brand's approved exemplars. If it fails, report that and drop the rule.

Keep the complete section id after the version folder in `--example`, including any slashes within the id.

Ask the person, with the rule and the test result. Adopt a rule only on the person's yes, with `ai-docs-kit rule adopt <rule> --theme <brand theme>`; never adopt one without it. An adopted rule enters the rulebook on probation, advisory until the person promotes it. Name the rule in the report. If the person says no, offer a dated line in `preferences.md` instead.
