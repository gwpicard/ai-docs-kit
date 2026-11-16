#import "/lib/marks.typ": section, el, fit-box
#import "/lib/frames.typ": content-frame, slide-title
#import "/lib/theme.typ": colour, type-style, space
#import "/lib/cite.typ": cite-keys

#let table(sec) = section(sec.id, {
  let items = sec.items
  let paragraphs = sec.paragraphs
  let source-line = sec.source_line
  let content = sec.at("content", default: (:))
  let data = sec.data
  let columns = data.at("columns", default: ())
  let rows = data.at("rows", default: ())
  let width = content-frame.w / calc.max(1, columns.len())
  let row-height = (content-frame.h - space(4)) / 11
  slide-title(sec + (title: el("title", sec.id, field: "title", sec.title)))
  place(top + left, dx: content-frame.x, dy: content-frame.y, {
    set block(above: 0pt, below: 0pt)
    set text(..type-style("slides", "body"), fill: colour("ink"))
    fit-box("figure", sec.id, content-frame.w, content-frame.h, {
      el("figure", sec.id, {
        place(top + left, dy: row-height - space(1), line(length: content-frame.w, stroke: 0.5pt + colour("hairline")))
        grid(
          columns: (width,) * columns.len(),
          ..columns.enumerate().map(((j, cell)) => fit-box("table-header", sec.id, width, row-height, el("table-header", sec.id, field: "data.columns[" + str(j) + "]", text(weight: "bold", str(cell)), width: width))),
          ..rows.enumerate().map(((r, row)) => row.enumerate().map(((c, cell)) => fit-box("table-cell", sec.id, width, row-height, el("table-cell", sec.id, field: "data.rows[" + str(r) + "][" + str(c) + "]", str(cell), width: width)))).flatten(),
        )
      }, width: content-frame.w)
      if source-line != "" {
        fit-box("figure-source", sec.id, content-frame.w, space(4), el("figure-source", sec.id, field: "source_line", source-line, width: content-frame.w))
      }
    })
    for (i, item) in items.enumerate() {
      let citations = sec.at("citations", default: ()).at(i, default: ())
      fit-box("item", sec.id, content-frame.w, row-height, el("item", sec.id, field: "items[" + str(i) + "].body", [#item.body #cite-keys(citations)]))
    }
  })
})
