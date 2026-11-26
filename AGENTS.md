# ai-docs-kit

Claude skills that write branded reports and decks as PDF, check every build against a brand rulebook, and learn from comments in Word and PowerPoint. Early development.

## Repository
Read `CONTEXT.md` for the vocabulary, `docs/DESIGN.md` for the skills and the review round trip, `docs/ENGINE.md` for the engine underneath, and `PLAN.md` for the decisions every issue follows.

Layout:
- `src/ai_docs_kit/`: the engine package and the `ai-docs-kit` command
- `skills/`: the Claude Code skills (`brand`, `create`, `review`)
- `agents/`: the subagents the skills spawn
- `tests/`: the tests
- `tests/judge/`: acceptance tests from earlier pieces. The kit's test lock refuses changes to existing tests unless an issue lists the path under `## Paths the builder may change`.
- `tests/fixtures/`: test fixtures
- `scripts/`: helper scripts
- `docs/`: design documents

Commands:
- `uv sync`: install dependencies
- `uv run python -m pytest`: run the tests
- `uv run ruff check .`: lint
- `uv run ruff format --check .`: check formatting
- `uv run mypy`: type-check
- `uv run ai-docs-kit doctor`: check the local setup

## Working rules
- Every rule ships with a seeded defect: a fixture that fails it and one that passes it.
- A change that affects rendering attaches the rendered pages.
- Skills and agents make no model calls of their own; the session's Claude is the model. Engine code that still calls Claude replays recorded cassettes in tests.
- Never patch generated files. Fix the source and rebuild.
- Never commit fonts or assets without a recorded licence.
- Never add a dependency without a licence check.
- Never name or copy material from a private project or a real brand.
- Open pull requests; do not push directly.
- One job per pull request.
- Sign off every commit under the DCO (`git commit -s`).
- Write British English.
- Use no em dashes.
- Put no agent attribution in commit messages or pull request bodies.

