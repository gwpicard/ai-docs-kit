# Outline

This is the one stop of the skill.

1. Build the outline from the document type: one line per section with its id, its intent, the facts it will use (by source key) and one sentence on what it says. Follow the type's required sections and length.
2. Show the person the outline, the gaps the material leaves and any question that only they can answer. Ask in one message.
3. Wait for the person to agree. Revise and show it again until they confirm. Do not draft anything before they approve it.
4. Once agreed, lay down the working file `<name>.md` for the structure only: front matter, the source list and one fenced section per outline line, each with its intent and a brief in `because=`. This is the only time you write the file directly. Run `ai-docs-kit check <name>.md --outline` to confirm that it fits the type.

After this, the person is not asked again until the version is ready. If a later stage finds that the outline must change, tell the person in the final report rather than stopping.
