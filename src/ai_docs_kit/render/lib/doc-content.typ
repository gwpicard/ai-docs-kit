// Shared document prose and lists. Field paths remain independent of reading order.

#import "marks.typ": el-full-width
#import "cite.typ": cite-keys

#let doc-content(sec, draw-item: none, draw-items: none, draw-data: none) = {
  let fallback = (
    ..sec.items.enumerate().map(((i, _)) => "items[" + str(i) + "]"),
    ..sec.paragraphs.enumerate().map(((i, _)) => "paragraphs[" + str(i) + "]"),
    "data",
  )
  let order = sec.at("content_order", default: fallback)
  for (position, field) in order.enumerate() {
    if field.starts-with("paragraphs[") {
      let i = int(field.slice(11, -1))
      el-full-width("paragraph", sec.id, field: field, par(sec.paragraphs.at(i)))
    } else if field.starts-with("items[") {
      if draw-items != none {
        if position == 0 or not order.at(position - 1).starts-with("items[") {
          let indices = ()
          for next-field in order.slice(position) {
            if not next-field.starts-with("items[") { break }
            indices.push(int(next-field.slice(6, -1)))
          }
          draw-items(indices)
        }
      } else if draw-item != none {
        draw-item(int(field.slice(6, -1)))
      }
    } else if field == "data" and draw-data != none {
      draw-data()
    }
  }
}

#let doc-list-item(sec, i) = {
  let item = sec.items.at(i)
  let field = "items[" + str(i) + "]"
  let citations = sec.at("citations", default: ()).at(i, default: ())
  list.item({
    el-full-width("list-item", sec.id, field: field, [#if item.head != "" { [#text(weight: "bold", item.head) ] }#item.body#if citations.len() > 0 { [ #cite-keys(citations)] }])
    for (j, sub) in item.at("sub", default: ()).enumerate() {
      list.item(el-full-width("list-sub", sec.id, field: field + ".sub[" + str(j) + "]", sub))
    }
  })
}
