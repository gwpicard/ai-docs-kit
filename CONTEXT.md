# Context

This file holds the project vocabulary: each thing has one word, used identically in code, UI and docs.

| Term | Meaning |
|---|---|
| **Project** | A folder: source material, one or more documents, their versions. |
| **Document** | One deliverable: a *working file* plus its builds. Format is `slides` or `doc`. |
| **Working file** | `<name>.md`. Front matter plus sections. The only editable state of a document. |
| **Section** | One outline line: one slide, or one component-sized block of a document page. Has a stable id. |
| **Intent** | What a section's content *is* (`key-numbers`, `comparison`, `quote`...). The author states intent; the chooser picks the component. |
| **Component** | Code that draws a section: a Typst function with a typed props schema and a capacity. |
| **Chooser** | Data table mapping intent plus content features to a component. |
| **Doctype** | A document type (`pitch-deck`, `report`...): outline, questions, checks, checklist. |
| **Theme** | The brand system for a project: tokens, components, rules, rubric, voice, exemplars. |
| **Token** | A named brand value (colour, type scale, spacing). |
| **Rule** | A named, testable requirement with severity, tier and remedy. |
| **Check** | The code or declarative spec that implements a rule. |
| **Finding** | One violation: rule, section, location, evidence, measured value. |
| **Fix** | A patch to a section that addresses a set of findings. |
| **Swatch** | A section rendered alone on its component's frame, for fast micro checks. |
| **Layout facts** | Machine-readable description of a rendered PDF: text runs, colours, boxes, plus semantic marks emitted by components. |
| **Look** | The pass that rasterises a build, runs all sensors and records the result. |
| **Critic** | The vision model call that judges screenshots against a closed rubric. |
| **Feedback** | A person's comment anchored to a section or region. |
| **Diagnosis** | The model's classification of why feedback arose. |
| **Learning** | A durable change to the theme produced from feedback or from repair history. |
| **Probation** | The period a new learning is advisory before it can block. |
| **Version** | An immutable build: outputs, build record, manifest, screenshots. |

## Skill words

The words the skills add, used the same way in skills, agents, code and docs:

- *Skill*: A Claude Code skill the person invokes: `brand`, `create` or `review`. A skill holds judgement and conversation; the engine holds everything deterministic.
- *Agent*: A subagent a skill spawns for one bounded job (`gather`, `write-section`, `look`, `review-classify`). It gets everything it needs in its prompt and returns a fixed shape.
- *Gathered facts*: Statements extracted from source material and agreed at the outline, each with a source key and optional locator, stored beside the working file for drafting.
- *Editable copy*: The `.pptx` (slides) or `.docx` (doc) written beside the PDF on every build, for a reviewer to edit text and comment in. The PDF is the deliverable; the editable copy is the review surface.
- *Look record*: What a build saw: the engine's findings plus the `look` agent's findings, stored in the version manifest. A version with an open error in its look record cannot be sent.
- *Sent version*: A version marked as given to a named reviewer. A returned copy is compared with the sent version, never with a fresh build.
- *Review copy*: An editable copy that came back from a reviewer, with edits, tracked changes or comments.
- *Review plan*: The engine's reading of a review copy: wording applied per section, and the items that need the person's yes (comments, deletions, reorders, unplaced text).
- *Redraft*: An ask written on a section (`redraft=`) that the `write-section` agent carries out from the section's own facts. A comment redrafts; it is never pasted in.
- *Plugin layer*: The engine, skills, agents, component library and neutral theme as installed. Shared, read-only in use, replaced on every update.
- *Person's layer*: What the person owns and grows: the brand folder (theme, rulebook, `preferences.md`), working files and versions. The plugin reads it and an update never writes it, except a migration the person runs.
- *Preferences*: The person's own instructions for how the skills work, kept dated in `preferences.md` in the brand folder. The skills read them before their first step.
