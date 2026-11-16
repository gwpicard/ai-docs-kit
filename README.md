# ai-docs-kit

> **Status: experimental.** Early development. Commands, file formats and the skills will change without notice, and
> there is no release yet. It is built in the open, partly by coding agents using
> [AI Loop Kit](https://github.com/gwpicard/ai-loop-kit).

Claude Code skills that write branded reports and decks.

- **`brand`** builds a brand from its guidelines, templates and approved examples: tokens, voice, and rules that each
  cite their source.
- **`create`** turns whatever is in a folder into a report or a deck. It agrees an outline with you, drafts it, renders
  the PDF, checks every page against the brand's rules and looks at it, and fixes what it finds before you see it.
- **`review`** reads the Word or PowerPoint copy that comes back with edits and comments, applies the wording,
  redrafts what the comments asked for, and rebuilds through the same checks. A comment that states a lasting
  preference can become a new brand rule.

The PDF is the deliverable. Every build also writes an editable copy for review: a PowerPoint deck that looks exactly
like the slides, or a Word document with the text.

- The design is in [`docs/DESIGN.md`](docs/DESIGN.md); the engine underneath is in [`docs/ENGINE.md`](docs/ENGINE.md).
- The decisions every change follows are in [`PLAN.md`](PLAN.md).

Licensed under Apache-2.0.
