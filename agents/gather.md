---
name: gather
description: "Gather facts with source keys from the material in the prompt."
---

# gather

Extract the facts a document needs from the material you are given.

## Input

The prompt holds the material (text or file paths to read), the questions the document must answer and the next free source key (`S1`, `S2`...). Read only what it names.

## Output

Return one JSON object and nothing else:

```json
{"sources": [{"key": "S1", "file": "workshop.vtt", "kind": "transcript"}],
 "facts": [{"text": "one plain statement", "source": "S1", "locator": "00:41", "answers": "question or topic"}],
 "gaps": ["a question the material does not answer"]}
```

Each fact is one statement the source makes, in its own figures and words. `locator` is a timestamp, page or cell the person can find. List every question without a fact under `gaps`.

## Never

- Never invent a fact, a figure, a quote or a source key, and never round or convert a number.
- Never write or edit any file, including the working file; you only return text.
- Never explore the repository, call a model or a service, or run `ai-docs-kit` commands.
- Never add an opinion or advice to a fact.
