// Shared theme drawing, with resolved type, colour and spacing tokens.
// The assembler supplies the marker to avoid a theme/marks import cycle.

#let title-block(front, version-date, mark, id, type-style: none, colour: none, space: none) = {
  // Include the full font metrics in each measured element, including descenders.
  set text(top-edge: "ascender", bottom-edge: "descender")
  block(breakable: false, below: space(3))[
    #mark("document-title", id, field: "front.title", {
      set text(..type-style("doc", "h1"), fill: colour("ink"))
      front.title
    })
    #if front.at("audience", default: "").trim() != "" {
      v(space(0))
      mark("document-audience", id, field: "front.audience", {
        set text(..type-style("doc", "body"), fill: colour("ink"))
        front.audience
      })
    }
    #if version-date != "" {
      v(space(0))
      mark("document-date", id, {
        set text(..type-style("doc", "caption"), fill: colour("muted"))
        version-date
      })
    }
  ]
}
