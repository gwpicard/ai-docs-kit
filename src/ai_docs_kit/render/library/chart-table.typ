// Chart as a table: the chart's twin table for A4 documents.

#import "/lib/marks.typ": section, el, el-full-width
#import "/lib/theme.typ": colour, type-style, space
#import "/lib/doc-content.typ": doc-content, doc-list-item

#let chart-table(sec) = section(sec.id, {
  let data-table = sec.chart.table
  let source-line = sec.source_line
  set text(fill: colour("ink"))
  block(sticky: true, breakable: false, el-full-width("heading", sec.id, field: "title", {
    set text(..type-style("doc", "h2"))
    sec.title
  }))
  set text(..type-style("doc", "body"))
  doc-content(sec, draw-item: i => doc-list-item(sec, i), draw-data: () => {
    if data-table == none {
      [chart type not supported]
    } else {
      let columns = data-table.columns
      el-full-width("figure", sec.id, layout(size => {
        let widths = (size.width / columns.len(),) * columns.len()
        let align-of = c => if c == 0 { left } else { right }
        let cell-pad = space(1)
        table(
          columns: widths,
          inset: (x: 0pt, y: cell-pad),
          stroke: none,
          table.header(
            repeat: true,
            ..columns.enumerate().map(((j, name)) => {
              let field = if j == 0 { if name != "" { "data.category_label" } else { none } } else { "data.series[" + str(j - 1) + "].name" }
              align(align-of(j), el("table-header", sec.id, field: field, width: widths.at(j), text(weight: "bold", name)))
            }),
            table.hline(stroke: 0.5pt + colour("hairline")),
          ),
          ..data-table.rows.enumerate().map(((i, row)) => row.enumerate().map(((j, cell)) => {
            let field = if j == 0 { "data.categories[" + str(i) + "]" } else { "data.series[" + str(j - 1) + "].values[" + str(i) + "]" }
            align(align-of(j), el("table-cell", sec.id, field: field, width: widths.at(j), cell))
          })).flatten(),
        )
      }))
    }
  })
  if source-line != "" {
    el-full-width("figure-source", sec.id, field: "source_line", {
      set text(..type-style("doc", "caption"), fill: colour("muted"))
      source-line
    })
  }
})
