#import "/lib/marks.typ": section, el, fit-box
#import "/lib/frames.typ": content-frame, slide-title
#import "/lib/theme.typ": colour, chart-role, type-style, space
#import "/lib/cite.typ": cite-keys

#let chart(sec) = section(sec.id, {
  let items = sec.items
  let paragraphs = sec.paragraphs
  let source-line = sec.source_line
  let content = sec.at("content", default: (:))
  let spec = sec.chart
  let categories = spec.categories
  let series = spec.series
  let kind = spec.type
  let plot-w = content-frame.w - 120pt
  let plot-h = categories.len() * calc.max(1, series.len()) * 15pt + if categories.len() <= 4 { space(7) } else { 0pt }
  slide-title(sec + (title: el("title", sec.id, field: "title", sec.title)))
  place(top + left, dx: content-frame.x, dy: content-frame.y, {
    fit-box("figure", sec.id, content-frame.w, content-frame.h, {
      el("figure", sec.id, {
        set text(..type-style("slides", "caption"), fill: colour("ink"))
        if kind != "bar" and kind != "column" {
          [chart type not supported]
        } else {
          let maximum = spec.scale.max
          let span = maximum - spec.scale.min
          let low = spec.scale.min
          el("chart-plot", sec.id, {
            if kind == "bar" {
              let rows = ()
              for (i, category) in categories.enumerate() {
                for (j, s) in series.enumerate() {
                  let value = s.values.at(i, default: 0)
                  rows.push(block(height: if categories.len() * series.len() <= 8 { 30pt } else { 18pt }, grid(columns: (120pt, plot-w * (calc.min(0, value) - low) / span, plot-w * calc.abs(value) / span), align: horizon, gutter: 0pt,
                    el("chart-label", sec.id, field: "data.categories[" + str(i) + "]", str(category)),
                    [],
                    el("chart-mark", sec.id, field: "data.series[" + str(j) + "].values[" + str(i) + "]", rect(width: plot-w * calc.abs(value) / span, height: 12pt, fill: chart-role(s.colour.palette, s.colour.index), stroke: none)),
                  )))
                }
              }
              stack(dir: ttb, spacing: 0pt, ..rows)
            } else {
              let slot = plot-w / calc.max(1, categories.len())
              let count = calc.max(1, series.len())
              block(width: content-frame.w, height: plot-h, {
                for (i, category) in categories.enumerate() {
                  for (j, s) in series.enumerate() {
                    let value = s.values.at(i, default: 0)
                    let length = plot-h * calc.abs(value) / span
                    let offset = plot-h * (maximum - calc.max(0, value)) / span
                    let x = 100pt + i * slot + j * slot / count
                    place(top + left, dx: x, dy: offset, el("chart-mark", sec.id, field: "data.series[" + str(j) + "].values[" + str(i) + "]", rect(width: slot / count * 0.7, height: length, fill: chart-role(s.colour.palette, s.colour.index), stroke: none)))
                  }
                }
              })
              let labels = ()
              for (i, category) in categories.enumerate() {
                for s in series {
                  labels.push(el("chart-label", sec.id, field: "data.categories[" + str(i) + "]", rotate(90deg, reflow: true, str(category))))
                }
              }
              pad(left: 100pt, grid(columns: (slot / count,) * labels.len(), ..labels))
            }
          })
          if spec.legend {
            el("chart-legend", sec.id, series.map(s => s.name).join("   "))
          }
        }
        if source-line != "" {
          el("figure-source", sec.id, field: "source_line", text(fill: colour("muted"), source-line))
        }
      })
    })
  })
})
