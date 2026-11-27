# Ship

Do not stop and do not ask the person anything in this stage.

1. Confirm that the latest version has a look record with no open error and carries the look agent's findings, recorded through `ai-docs-kit look <version> --findings <file>`. An empty array counts; the engine page pass alone does not. If not, the look stage has already used its two fix rounds, so report what remains and do not describe the version as ready to ship.
2. Give the person the paths: the PDF, the editable copy (`<name>.docx` or `<name>.pptx`) and the version folder. Say how many pages were looked at, how many warnings remain and in which sections.
3. Name any open error, any page the engine page pass could not check and any missing look agent findings; the person decides what to send. Use the summary line of `ai-docs-kit look <version> --findings <file>` for the engine page pass and error counts. Do not edit the version's records by hand.
4. Tell the person that a reviewed copy of this version comes back through the `review` skill, which compares it with the version it came from.
