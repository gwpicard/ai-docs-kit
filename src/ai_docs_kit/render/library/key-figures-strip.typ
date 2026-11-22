// Document key figures: a strip kept together, using the document's type scale.

#import "/lib/marks.typ": section, el, el-full-width
#import "/lib/theme.typ": colour, type-style, space
#import "/lib/cite.typ": cite-keys

#let key-figures-strip(sec) = section(sec.id, block(breakable: false, {
  set text(fill: colour("ink"))
  el-full-width("heading", sec.id, field: "title", {
    set text(..type-style("doc", "h1"))
    sec.title
  })
  layout(size => {
    let gutter = space(4)
    let width = (size.width - gutter * calc.max(0, sec.items.len() - 1)) / calc.max(1, sec.items.len())
    grid(
      columns: (width,) * sec.items.len(),
      column-gutter: gutter,
      ..sec.items.enumerate().map(((i, item)) => {
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
  if sec.source_line != "" {
    el-full-width("source", sec.id, field: "source_line", {
      set text(..type-style("doc", "caption"), fill: colour("muted"))
      sec.source_line
    })
  }
}))
