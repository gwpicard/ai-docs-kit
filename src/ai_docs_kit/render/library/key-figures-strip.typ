// Document key figures: a strip kept together, using the document's type scale.

#import "/lib/marks.typ": section, el, el-full-width
#import "/lib/theme.typ": colour, type-style, space
#import "/lib/cite.typ": cite-keys
#import "/lib/doc-content.typ": doc-content

#let figure-strip(sec, indices) = layout(size => {
  let gutter = space(4)
  let width = (size.width - gutter * calc.max(0, indices.len() - 1)) / calc.max(1, indices.len())
  grid(
    columns: (width,) * indices.len(),
    column-gutter: gutter,
    ..indices.map(i => {
      let item = sec.items.at(i)
      let field = "items[" + str(i) + "]"
      let citations = sec.at("citations", default: ()).at(i, default: ())
      el("figure-value", sec.id, field: field + ".head", width: width, {
        set text(..type-style("doc", "h1"), fill: colour("accent"))
        item.head
      })
      el("figure-caption", sec.id, field: field + ".body", width: width, {
        set text(..type-style("doc", "body"))
        item.body
      })
      if citations.len() > 0 {
        el("figure-citation", sec.id, width: width, {
          set text(..type-style("doc", "caption"))
          cite-keys(citations)
        })
      }
    }),
  )
})

#let key-figures-strip(sec) = section(sec.id, {
  let content = {
    set text(fill: colour("ink"))
    block(sticky: true, breakable: false, el-full-width("heading", sec.id, field: "title", {
      set text(..type-style("doc", "h1"))
      sec.title
    }))
    set text(..type-style("doc", "body"))
    doc-content(sec, draw-items: indices => {
      // Values stay in one strip; prose flows outside its unbreakable block.
      if sec.paragraphs.len() == 0 { figure-strip(sec, indices) }
      else { block(breakable: false, figure-strip(sec, indices)) }
    })
    if sec.source_line != "" {
      el-full-width("source", sec.id, field: "source_line", {
        set text(..type-style("doc", "caption"), fill: colour("muted"))
        sec.source_line
      })
    }
  }
  if sec.paragraphs.len() == 0 { block(breakable: false, content) }
  else { content }
})
