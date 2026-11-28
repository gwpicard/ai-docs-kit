// Body section: a title, prose and lists that flow across pages.

#import "/lib/marks.typ": section, el-full-width
#import "/lib/theme.typ": colour, type-style
#import "/lib/doc-content.typ": doc-content, doc-list-item

#let body(sec) = section(sec.id, {
  set text(fill: colour("ink"))
  block(sticky: true, breakable: false, el-full-width("heading", sec.id, field: "title", {
    set text(..type-style("doc", "h1"))
    sec.title
  }))
  set text(..type-style("doc", "body"))
  doc-content(sec, draw-item: i => doc-list-item(sec, i))
  if sec.source_line != "" {
    el-full-width("source", sec.id, field: "source_line", {
      set text(..type-style("doc", "caption"), fill: colour("muted"))
      sec.source_line
    })
  }
})
