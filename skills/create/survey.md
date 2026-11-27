# Survey

Find out where the work stands before asking the person anything.

1. List the project folder. Note the material the person dropped in (transcripts, notes, spreadsheets, decks), any `<name>.md` working file and any `<name>.versions/` folder.
2. If a working file exists, read its front matter and run `ai-docs-kit section list <name>.md`. Resume from the first stage whose result is missing: no facts means gather, no agreed outline means outline, empty sections mean draft, no look record in the latest version means look, a clean look means ship.
3. If none exists, name the document type from what the person said (`report` for a document, `pitch-deck` for a deck). Read the type's questions and ask only those the material does not already answer, all in one message. Do not ask what the material states.
4. For an existing working file, run `ai-docs-kit theme which <name>.md --json` and use its `path` as the theme. Report a refusal with its candidates; do not pick a theme yourself. For a new document, defer this command until the outline stage creates the working file.

Hand the next stage the folder, the document type, the format, the brand and the material list.
