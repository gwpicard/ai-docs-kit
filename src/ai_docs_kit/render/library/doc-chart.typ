// Flowing A4 charts share the slide geometry, sized to the document column.
#import "/lib/marks.typ": section, el-full-width
#import "/lib/theme.typ": colour, type-style, space
#import "/lib/doc-content.typ": doc-content, doc-list-item
#import "/lib/chart-drawing.typ": draw-chart-plot, draw-chart-legend
#import "chart-table.typ": chart-table

#let doc-chart(sec) = if sec.chart.type == "unsupported" {
  chart-table(sec)
} else {
  section(sec.id, {
    set text(fill: colour("ink"))
    block(sticky: true, breakable: false, el-full-width("heading", sec.id, field: "title", {
      set text(..type-style("doc", "h2"))
      sec.title
    }))
    set text(..type-style("doc", "body"))
    doc-content(sec, draw-item: i => doc-list-item(sec, i), draw-data: () => {
      el-full-width("figure", sec.id, layout(size => {
        set text(..type-style("doc", "caption"))
        let spec = sec.chart
        let count = calc.max(1, spec.series.len())
        // Size grouped rows and their gaps from the available document width.
        let row-h = calc.min(12pt, size.width / (spec.categories.len() * (count + 1)))
        let label-w = if spec.type == "bar" { calc.min(120pt, size.width / 4) } else { 0pt }
        draw-chart-plot(sec, size.width, size.width / 2,
          label-width: label-w, column-inset: 0pt, label-gap: space(1),
          row-height: row-h, mark-height: row-h * 0.8, group-gap: row-h,
        )
        v(space(2))
        draw-chart-legend(sec, width: size.width)
      }))
    })
    if sec.source_line != "" {
      el-full-width("figure-source", sec.id, field: "source_line", {
        set text(..type-style("doc", "caption"), fill: colour("muted"))
        sec.source_line
      })
    }
  })
}
