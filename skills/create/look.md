# Look

Do not stop and do not ask the person anything in this stage. A person who has agreed the outline has agreed to this loop.

1. Print the pages for the agent with `ai-docs-kit look <version> --pages`. Give the `look` agent the listing and the page images in the version's `pages/` folder. It returns a JSON array only.
2. Save the array to a file and record it with `ai-docs-kit look <version> --findings <file>`. If the command rejects it (an unknown section or page, an unknown severity), send the agent the message once and record the corrected array. An empty array is valid: it means every page was looked at and nothing was found.
3. Fix what was found, by section. For each section with an error or a warning, run `ai-docs-kit section brief <name>.md <id>`, adding `--theme <brand theme>` when the build uses a brand theme. Pass the command's output to a `write-section` agent alongside the finding, so its repair follows the voice rules, terminology and chosen component's capacity limits. Write the result only through `ai-docs-kit section put <name>.md <id> --from <block file>`; never edit the working file directly. Findings that name no section (a page-level fault) go to the nearest section on that page.
4. Rebuild with `ai-docs-kit build <name>.md`, then look at the new version again from step 1.

Run at most two fix rounds. After the second rebuild and look, stop fixing. Report what remains by section: the section id, its title, the page, the severity and the message, with the errors first. Do not hide a remaining error or reword it.

A remaining error ends the skill here with the report, not at ship.
