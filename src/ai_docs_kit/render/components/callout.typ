// Callout section: one framed block with a title and a list of items; it never breaks.

#import "/lib/marks.typ": section, el, el-full-width
#import "/lib/theme.typ": colour, type-style, space
#import "/lib/cite.typ": cite-keys
#import "/lib/doc-content.typ": doc-content

#let callout(sec) = section(sec.id, {
  set text(..type-style("doc", "body"), fill: colour("ink"))
  el-full-width("callout", sec.id, block(
    width: 100%,
    breakable: false,
    inset: space(5),
    stroke: 1pt + colour("accent"),
    {
      el-full-width("callout-title", sec.id, field: "title", text(..type-style("doc", "h1"), sec.title))
      doc-content(sec, draw-item: i => {
        let item = sec.items.at(i)
        let citations = sec.at("citations", default: ()).at(i, default: ())
        let field = "items[" + str(i) + "]"
        list.item({
          el("callout-item", sec.id, field: field)[#text(weight: "bold", item.head) #item.body#if citations.len() > 0 { [ #cite-keys(citations)] }]
          for (j, sub) in item.at("sub", default: ()).enumerate() {
            list.item(el-full-width("list-sub", sec.id, field: field + ".sub[" + str(j) + "]", sub))
          }
        })
      })
    },
  ))
})
