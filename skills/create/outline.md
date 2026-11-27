# Outline

This is the one stop of the skill.

Read [working-file.md](working-file.md) for the front matter, sources, section
syntax and allowed intents before proposing or writing the outline.

1. Build the outline from the document type: one line per section with its id, its intent, the facts it will use (by source key) and one sentence on what it says. Follow the type's required sections and length.
2. Show the person the outline, the gaps the material leaves and any question that only they can answer. Ask in one message.
3. Wait for the person to agree. Revise and show it again until they confirm. Do not draft anything before they approve it.
4. Once agreed, lay down the working file `<name>.md` for the structure only: front matter, the source list and one fenced section per outline line, each with its intent and a brief in `because=`. This is the only time you write the file directly. Run `ai-docs-kit check <name>.md --outline` to confirm that it fits the type.
5. Write the agreed facts as a JSON array in `<facts.json>`, using each fact's `text`, `source` and optional `locator` from the gather agent. Run `ai-docs-kit facts add <name>.md <facts.json>` before drafting. It validates source keys and checks every figure against the source at its locator before storing the batch atomically under `.ai_docs_kit/` beside the working file. Read them back with `ai-docs-kit facts list <name>.md`.

`facts add` refuses a derived figure stored as a plain fact when the source does
not state it. Record it as a `calc:` line after the facts supplying its operands,
either already stored or earlier in the same batch. The guard recomputes `sum`,
`difference`, `ratio` and `percentage`, rounded to the result's decimal places.
For example, cite the cost fact from `[S1 p.4]` and trips fact from `[S2 00:41]`:

```json
[
  {"text": "The service cost £184,000.", "source": "S1", "locator": "p.4"},
  {"text": "The service ran 61,300 trips.", "source": "S2", "locator": "00:41"},
  {"text": "calc: ratio(184000, 61300) = 3.00", "source": "S1"}
]
```

When drafting the figure, cite both operand facts beside it and repeat the
calculation in the section's note:

```markdown
The cost per trip was £3.00. [S1 p.4] [S2 00:41]
> note: calc: ratio(184000, 61300) = 3.00
```

Local source paths resolve beside the working file. Missing or unreadable local
sources are refused. URL facts are accepted with a persistent `unverified` mark
and a warning; report that evidence limit when presenting the outline.

After this, the person is not asked again until the version is ready. If a later stage finds that the outline must change, tell the person in the final report rather than stopping.
