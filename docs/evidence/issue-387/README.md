# Issue 387 rendering evidence

These pages come from the real CLI builds in the unchanged locked
`tests/test_doc_page_breaks.py` and the additional paired CLI cases in
`tests/test_doc_page_break_continuations.py`. Each folder retains every rendered
page; the tests provide the synthetic working files. All 38 pages were inspected
for page breaks, clipping, repeated headers and matching heading sizes.
The `fail` inputs seed the original
defects; the pages show the corrected output. The `pass` inputs are readable
controls. The restyled callout case uses a document h1 size of 23 pt instead
of the neutral theme's 16 pt; both neighbouring labels follow that token.

Working files and page images are project-authored material under the
repository's MIT licence. They use the existing neutral theme and its recorded
font licences. No fonts, external assets or generated PDFs are added.

The saved layout facts check heading and first-text pages, item head and first
body line pages, every repeated table header above its cells, retained table
values and matching callout and body heading sizes. Additional cases keep chart
and key-figure headings with opening prose and allow an item longer than a page
to continue, while a short headed item stays inline.

| Case | Input | Rendered pages |
|---|---|---|
| heading-body | pass | [1](heading-body/pass/p01.png) |
| heading-body | fail | [1](heading-body/fail/p01.png), [2](heading-body/fail/p02.png) |
| heading-bullets | pass | [1](heading-bullets/pass/p01.png) |
| heading-bullets | fail | [1](heading-bullets/fail/p01.png), [2](heading-bullets/fail/p02.png) |
| item-body | pass | [1](item-body/pass/p01.png) |
| item-body | fail | [1](item-body/fail/p01.png), [2](item-body/fail/p02.png) |
| item-bullets | pass | [1](item-bullets/pass/p01.png) |
| item-bullets | fail | [1](item-bullets/fail/p01.png), [2](item-bullets/fail/p02.png) |
| table-two-pages | pass | [1](table-two-pages/pass/p01.png) |
| table-two-pages | fail | [1](table-two-pages/fail/p01.png), [2](table-two-pages/fail/p02.png) |
| table-reordered | pass | [1](table-reordered/pass/p01.png) |
| table-reordered | fail | [1](table-reordered/fail/p01.png), [2](table-reordered/fail/p02.png), [3](table-reordered/fail/p03.png), [4](table-reordered/fail/p04.png) |
| callout-neutral | pass | [1](callout-neutral/pass/p01.png) |
| callout-neutral | fail | [1](callout-neutral/fail/p01.png) |
| callout-restyled | pass | [1](callout-restyled/pass/p01.png) |
| callout-restyled | fail | [1](callout-restyled/fail/p01.png) |
| heading-chart | pass | [1](heading-chart/pass/p01.png) |
| heading-chart | fail | [1](heading-chart/fail/p01.png), [2](heading-chart/fail/p02.png) |
| heading-key-figures | pass | [1](heading-key-figures/pass/p01.png) |
| heading-key-figures | fail | [1](heading-key-figures/fail/p01.png), [2](heading-key-figures/fail/p02.png) |
| long-item-body | pass | [1](long-item-body/pass/p01.png) |
| long-item-body | fail | [1](long-item-body/fail/p01.png), [2](long-item-body/fail/p02.png), [3](long-item-body/fail/p03.png) |
| long-item-bullets | pass | [1](long-item-bullets/pass/p01.png) |
| long-item-bullets | fail | [1](long-item-bullets/fail/p01.png), [2](long-item-bullets/fail/p02.png), [3](long-item-bullets/fail/p03.png) |
