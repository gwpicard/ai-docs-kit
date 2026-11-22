# Gather

Collect the facts the document will rest on, each with a source key.

1. Give the `gather` agent the paths of the material and the questions the document must answer. It returns a JSON object with `sources`, `facts` and `gaps`. Each fact has `text`, a `source` key and an optional `locator` (a timestamp, a page or a cell). Run it once per source when there are many, in parallel.
2. Read what comes back. Drop any fact whose locator you cannot find in the source. Merge duplicates and keep the earlier source key.
3. Keep the facts and the source list for the outline. The working file lists each source as `- [S1] <file>, <kind>` under its `## Sources` heading; the file is written at the outline stage, once the person has agreed it.
4. When resuming, read the stored facts with `ai-docs-kit facts list <name>.md` and the sections with `ai-docs-kit section list <name>.md`, and gather only what is missing. After agreeing any new facts, save their JSON array through `ai-docs-kit facts add <name>.md <facts.json>`; every source key must already be in the working file's source list.
5. Note what the material does not cover. The outline reports these gaps to the person; do not fill them with guesses.

Do not stop to ask here. Anything open goes into the outline for the person to settle.
