# Document bar and column charts

These pages were rendered through `ai-docs-kit build` with the neutral theme.
Each Markdown file beside its page is the synthetic source for that build.
PDFs, editable copies and build records stay in the build's temporary folder.

![Twelve months and three zones on one A4 page](monthly-column-p01.png)

![Six categories shown as grouped horizontal bars](six-category-bar-p01.png)

![Twenty-four categories and five series as horizontal bars](capacity-bar-p01.png)

![Twenty-four categories and five series as columns](capacity-column-p01.png)

![An unsupported pie type falls back to the twin table](fallback-pie-p01.png)

The capacity examples draw all 120 values. Column labels reserve a gap before
choosing whether to rotate, so adjacent category words remain distinct in PDF
text extraction as well as on the page. Prose follows working-file order and
the source line follows the chart or table.

The merge regression in `tests/test_doc_page_break_continuations.py` builds
`chart-heading.md` through the CLI. Before the fix, the heading ends page 1
and its opening prose starts page 2. The document chart now keeps them
together, matching the other document components.

![Before: heading stranded at the foot of page 1](chart-heading-before-p01.png)

![Before: prose starts on page 2](chart-heading-before-p02.png)

![After: preceding section ends page 1](chart-heading-after-p01.png)

![After: heading and opening prose share page 2](chart-heading-after-p02.png)

All wording and data are synthetic, and these renderings are original project
material under the repository's MIT licence. The existing Inter and Source
Serif 4 fonts are licensed under the SIL Open Font Licence, recorded in
`src/ai_docs_kit/themes/neutral/fonts/LICENSES.txt`. No outside asset or new font
was added.
