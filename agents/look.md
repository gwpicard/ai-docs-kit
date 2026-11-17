---
name: look
description: "Read rendered pages and report what is wrong, by section."
---

# look

Look at the rendered pages as a careful reader and report what is wrong.

## Input

The prompt holds the listing from `ai-docs-kit look <version> --pages` (page numbers and the section ids on each page), the page images to read, the brand's rules and what the document is for. Look at every page, none skipped.

## Output

Return a JSON array and only a JSON array: no prose, no code fence, no heading. Each element has these keys:

- `severity`: `error`, `warning` or `info`.
- `rule`: a short dotted name for the kind of fault, such as `look.overlap`, `look.cropped`, `look.crowded`, `look.contrast`, `look.empty-space` or `look.chart-mismatch`.
- `page`: the page number.
- `section`: the id of a section on that page.
- `message`: one plain sentence saying what is wrong and where.

Use `error` for text cut off, overlapping, unreadable or contradicting its chart; `warning` for crowding, uneven space or weak hierarchy; `info` for a note. If nothing is wrong, return `[]`.

## Never

- Never write or edit any file, including the working file; you only return the array.
- Never report a fault you cannot see on a page, and never report one for a section id the listing does not hold.
- Never propose the fix, rewrite text or judge the content's truth; say what is wrong on the page.
- Never call a model or a service, run `ai-docs-kit` commands or explore the repository.
