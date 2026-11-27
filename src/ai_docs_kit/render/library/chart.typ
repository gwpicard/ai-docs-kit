#import "/lib/marks.typ": section, el, fit-box
#import "/lib/frames.typ": content-frame, slide-title
#import "/lib/theme.typ": colour, type-style, space
#import "/lib/chart-drawing.typ": draw-chart-plot, draw-chart-legend

#let chart(sec) = section(sec.id, {
  let items = sec.items
  let paragraphs = sec.paragraphs
  let source-line = sec.source_line
  let content = sec.at("content", default: (:))
  let spec = sec.chart
  let categories = spec.categories
  let series = spec.series
  let kind = spec.type
  let plot-h = categories.len() * calc.max(1, series.len()) * 15pt + if categories.len() <= 4 { space(7) } else { 0pt }
  slide-title(sec + (title: el("title", sec.id, field: "title", sec.title)))
  place(top + left, dx: content-frame.x, dy: content-frame.y, {
    fit-box("figure", sec.id, content-frame.w, content-frame.h, {
      el("figure", sec.id, {
        set text(..type-style("slides", "caption"), fill: colour("ink"))
        if kind != "bar" and kind != "column" {
          [chart type not supported]
        } else {
          draw-chart-plot(sec, content-frame.w, plot-h)
          draw-chart-legend(sec)
        }
        if source-line != "" {
          el("figure-source", sec.id, field: "source_line", text(fill: colour("muted"), source-line))
        }
      })
    })
  })
})
