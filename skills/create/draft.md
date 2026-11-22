# Draft

Do not stop and do not ask the person anything in this stage; the outline was agreed.

Read [working-file.md](working-file.md) for the section syntax and allowed intents,
and include the relevant parts in each agent's prompt. Before drafting, confirm
the outline stage saved the agreed facts with
`ai-docs-kit facts add <name>.md <facts.json>`; if that step is missing, save them
now using the agreed gather array and the working file's source list.

1. Read the agreed facts with `ai-docs-kit facts list <name>.md`. For each section, start one `write-section` agent, all in parallel. Give each its id, its brief, its intent, the facts it may use with their source keys, the brand's voice rules and the section as it stands (from `ai-docs-kit section get <name>.md <id>`).
2. Each agent returns one section block. Write it back only through `ai-docs-kit section put <name>.md <id> --from <block file>`. Never edit the working file directly in this stage. If `section put` refuses a block (a guard, an unknown source key, a locked or human-owned section), do not force it: re-brief the agent once with the refusal, and if it refuses again, leave the section and list it in the final report.

   The fact guard accepts figures, dates and names supported by the stored gathered facts, source list, front matter or section's previous text. Citation locators are source metadata, not claim numbers; source keys are checked in both prose and bullets. A new number without evidence is still refused with `fact-unsupported`.
3. Write summary sections last, from the finished text of the others, with no new facts.
4. Build: `ai-docs-kit build <name>.md`, adding `--theme <brand theme>` when the brand has one. The build writes the PDF, the editable copy and a new version, and runs the checks. Read the engine's findings. An error that is not a look matter (a missing source, an invalid section) goes back to the section's agent through `section put`.

Hand the version folder to the look stage.

For documents, use `bullets` for headed or plain list items, including sub-lines
and citations, and `key-numbers` for 2 to 4 values with labels. These render in
the document style and stay editable as lists in the Word copy.
