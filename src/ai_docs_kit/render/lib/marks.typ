// Marks: metadata labelled <ai_docs_kit-mark>, told apart by `kind`.
// Positions are in pt as numbers.

#import "theme.typ": colour

#let _pos() = {
  let p = here().position()
  (page: p.page, x: p.x / 1pt, y: p.y / 1pt)
}

#let section(id, body) = {
  context [#metadata((kind: "section", id: id, edge: "start", .._pos())) <ai_docs_kit-mark>]
  body
  context [#metadata((kind: "section", id: id, edge: "end", .._pos())) <ai_docs_kit-mark>]
}

// The body always sits in a block, so the mark reports the top edge, not a baseline.
#let el(role, sec-id, body, width: auto, field: none) = context {
  let b = block(width: width, body)
  let m = measure(b)
  [#metadata((kind: "element", role: role, id: sec-id, .._pos(), w: m.width / 1pt, h: m.height / 1pt, field: field)) <ai_docs_kit-mark>]
  b
}

// `el` measures outside any container, where 100% resolves to 0, so pass the available width.
#let el-full-width(role, sec-id, body, field: none) = layout(size => el(role, sec-id, width: size.width, field: field, body))

#let fit-box(role, sec-id, w, h, body) = context {
  let m = measure(block(width: w, body))
  [#metadata((kind: "fit", role: role, id: sec-id, need: m.height / 1pt, have: h / 1pt, ok: m.height <= h)) <ai_docs_kit-mark>]
  block(width: w, height: h, clip: true)[
    #body
    #if m.height > h {
      place(bottom, rect(width: w, height: 3pt, fill: colour("accent"), stroke: none))
    }
  ]
}
