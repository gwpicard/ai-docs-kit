# Issue 386 rendering evidence

These pages come from the real CLI builds in the unchanged
`tests/test_doc_section_content.py`. Each folder includes its synthetic working
file and every rendered page. The pages were inspected for order, clipping and
the callout frame. No generated PDF is committed.

The synthetic working files and page images are project-authored material under
the repository's MIT licence. They use the existing neutral theme and its
recorded font licences; no fonts are added.

| Build | Pages | What it exercises |
|---|---|---|
| [Prose first](prose-first/p01.png) | 1 | All five components, paragraph and item field anchors, sub-lines, citations and chart data. |
| [Interleaved](interleaved/p01.png) | 1 | Prose between list items and after the figure strip, following the owner's order decision. |
| Long prose before the strip | [1](long-prose-before-strip/p01.png), [2](long-prose-before-strip/p02.png) | A paragraph flows across pages before the unbreakable strip. |
| Long prose after the strip | [1](long-prose-after-strip/p01.png), [2](long-prose-after-strip/p02.png) | A paragraph flows across pages after the unbreakable strip. |

`tests/test_doc_content_order_round_trip.py` additionally builds after two
`section get`/`section put` saves, compares PDF and Word order, covers chart data
before prose and keeps prose between separate figure lists. The existing
`tests/test_components.py` checks every component against its unchanged golden
facts. The model schemas were regenerated with
`uv run python -m ai_docs_kit.model.schema docs/schemas`.

## Chart review regression

The additional pages below come from build, Word-copy edits, `review read`,
`review apply` and a second real build in
`tests/test_chart_word_reference_round_trip.py`. The chart prose was edited to
"Opening wording revised.". The generated Word reference stays out of the chart's
PDF prose. The separate body section deliberately retains identical literal text.

| Build | Rebuilt page |
|---|---|
| Data before prose | [Page 1](chart-review-data-first/p01.png) |
| Data between paragraphs | [Page 1](chart-review-data-between/p01.png) |
| Data after prose | [Page 1](chart-review-data-last/p01.png) |

The same regression file covers older copies without the reference style,
paragraph insertions, deletions and splits, moved references, literal prose
identical to a generated reference, and edited or cleared reference-only charts.
The review-plan schema was regenerated with `export_review_schema` from
`ai_docs_kit.review.plan`.
