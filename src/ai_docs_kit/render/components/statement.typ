// Statement slide: one title in a fixed frame.

#import "/lib/marks.typ": section, el, fit-box
#import "/lib/theme.typ": colour, type-style
#import "/lib/frames.typ": content-frame
#import "/lib/cite.typ": cite-keys

#let statement(sec) = section(sec.id, {
  set text(fill: colour("ink"))
  place(top + left, dx: content-frame.x, dy: content-frame.y, fit-box("title", sec.id, content-frame.w, 300pt, {
    set text(..type-style("slides", "figure"))
    let paragraphs = sec.at("paragraphs", default: ())
    if sec.items.len() > 0 {
      el("title", sec.id, field: "title", sec.title)
    } else if paragraphs.len() > 0 {
      el("title", sec.id, sec.title)
    } else {
      sec.title
    }
    for (i, p) in paragraphs.enumerate() {
      parbreak()
      set text(..type-style("slides", "body"))
      el("paragraph", sec.id, field: "paragraphs[" + str(i) + "]", p)
    }
    for (i, item) in sec.items.enumerate() {
      parbreak()
      set text(..type-style("slides", "body"))
      let citations = sec.at("citations", default: ()).at(i, default: ())
      el("item", sec.id, field: "items[" + str(i) + "].body", [#item.body#if citations.len() > 0 { [ #cite-keys(citations)] }])
    }
  }))
})
