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

## Install

You need [Claude Code](https://claude.com/claude-code) and [`uv`](https://docs.astral.sh/uv/), which runs the engine
from the plugin folder. The engine needs no API key.

1. In Claude Code, add this repository as a plugin marketplace: `/plugin marketplace add gwpicard/ai-docs-kit`.
2. Install the plugin: `/plugin install ai-docs-kit@ai-docs-kit`.
3. Restart Claude Code, then type `/` and check that `brand`, `create` and `review` are listed.

## Five-minute live test

Run this in Claude Code, in an empty folder. It uses the neutral theme, so no brand work is needed first.

1. Make an empty folder, open Claude Code in it, and ask `/create` for a short report on any topic you can describe
   in a few sentences. Agree the outline when it is offered.
2. Wait for the build. Check that the folder now holds `<name>.md`, a `build/` folder with the PDF and a Word copy,
   and a `<name>.versions/` folder. Open the PDF and check that it matches what the skill reported.
3. Open the Word copy. Reword a sentence, add a comment on another section (for example, "say how many"), and delete
   a third section. Save it beside the original under a new name.
4. Ask `/review` to read it. Check that it lists your wording, your comment and the deleted section, and asks you to
   confirm the comment and the deletion before it changes anything.
5. Confirm both. Check that the new version keeps your sentence, that the commented section carries a `redraft=` ask
   in `<name>.md`, that the deleted section is gone, and that the PDF is rebuilt.
6. Optional: run `/brand` on a short guidelines file and build again to see the brand's rules apply.

If every check holds, the round trip works. `tests/test_round_trip.py` runs the same path on fixtures without a model.

Licensed under the MIT License.
