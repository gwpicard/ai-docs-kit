# Release eval

Before each release, the owner runs this suite after #277, #278 and #279 have
landed. It makes live model calls and consumes the owner's model usage or API
budget. It is not run by CI or the loop. The deterministic structure and seeded
grader checks run offline in `tests/test_create_plugin_eval.py`.

From the plugin root, with the engine's usual prerequisites installed and a
working Claude Code session's authentication available, run:

```sh
claude plugin eval . --allow-tools Bash Write Edit --runs 1 --max-cost-usd <n> --scaffold --no-publish
```

Replace `<n>` with the owner's chosen dollar ceiling before running. Use a
Claude Code version supporting `plugin eval`, with a working shell sandbox.
Review the local plugin trust prompt if one appears. The scaffold flag is
required: without it the three source files are not created. The scaffold
writes only synthetic source text into each run's empty working folder; it
does not supply a working file, gathered facts or a build.

The run agrees the first outline through `append_system_prompt`, then exercises
gathering, drafting, building and looking through the installed plugin. Read
the local report under `evals/results/` and require every with-plugin grader to
pass, including the Skill invocation indicator. A partial run or a run that
reaches a cost, time or turn limit is not a release pass. By default the runner
also runs a no-plugin baseline; the Skill indicator is not included in that
comparison's score. One run is a release smoke check, not a reliability estimate.

The manifest checks deliberately inspect v1: a failure in the first build is
visible even if a later repair succeeds. The regex graders check text records,
not the visual quality or binary contents of the PDF and Word copy. The look
must be recorded and clean, with no engine or agent error. Citations are checked
for presence beside drafted text, not for semantic entailment.

Format and runner details: [Claude Code plugin evals](https://code.claude.com/docs/en/plugin-evals.md).
