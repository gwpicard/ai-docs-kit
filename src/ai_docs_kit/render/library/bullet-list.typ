// Document list: headed or plain items with citations and nested sub-lines.

#import "/lib/marks.typ": section, el-full-width
#import "/lib/theme.typ": colour, type-style
#import "/lib/cite.typ": cite-keys

#let bullet-list(sec) = section(sec.id, {
  set text(fill: colour("ink"))
  el-full-width("heading", sec.id, field: "title", {
    set text(..type-style("doc", "h1"))
    sec.title
  })
  set text(..type-style("doc", "body"))
  for (i, item) in sec.items.enumerate() {
    let field = "items[" + str(i) + "]"
    let citations = sec.at("citations", default: ()).at(i, default: ())
    list.item({
      el-full-width("list-item", sec.id, field: field, [#if item.head != "" { [#text(weight: "bold", item.head) ] }#item.body#if citations.len() > 0 { [ #cite-keys(citations)] }])
      for (j, sub) in item.at("sub", default: ()).enumerate() {
        list.item(el-full-width("list-sub", sec.id, field: field + ".sub[" + str(j) + "]", sub))
      }
    })
  }
  if sec.source_line != "" {
    el-full-width("source", sec.id, field: "source_line", {
      set text(..type-style("doc", "caption"), fill: colour("muted"))
      sec.source_line
    })
  }
})
