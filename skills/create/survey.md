# Survey

Find out where the work stands before asking the person anything.

1. List the project folder. Note the material the person dropped in (transcripts, notes, spreadsheets, decks), any `<name>.md` working file and any `<name>.versions/` folder.
2. If a working file exists, read its front matter and run `ai-docs-kit section list <name>.md`. Resume from the first stage whose result is missing: no facts means gather, no agreed outline means outline, empty sections mean draft, no look record in the latest version means look, a clean look and no sent date means ship.
3. If none exists, name the document type from what the person said (`report` for a document, `pitch-deck` for a deck). Read the type's questions and ask only those the material does not already answer, all in one message. Do not ask what the material states.
4. Pick the brand: the person's `.brand/<slug>/theme` if one exists, otherwise the neutral theme.

Hand the next stage the folder, the document type, the format, the brand and the material list.
