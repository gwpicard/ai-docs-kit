---
tags: [create, release]
expected_outcome: A drafted, cited report with a PDF, Word copy and recorded clean look.
max_turns: 100
timeout_seconds: 1800
allowed_tools: [Read, Glob, Grep, Skill, Agent, Bash, Write, Edit]
append_system_prompt: >-
  The person agrees the first outline you offer, including its facts and gaps.
  Show that outline, treat this as their approval, and continue through drafting,
  building and looking at every page without waiting for another message.
---
Please write a short report from notes.txt, results.txt and next-steps.txt in
this folder. The readers are the trial team, who know the collection process;
the purpose is to help them decide whether to repeat the trial. Use the neutral
theme and British English. Include an introduction, the results and a finding
about the next step, with source citations in at least three drafted sections.
Save the working file as report.md and give me the PDF and editable Word copy
in build/, after looking at every rendered page.
