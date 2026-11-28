// Shared bar, column and line geometry. Callers supply their page's available width.
#import "marks.typ": el
#import "theme.typ": chart-role

#let draw-chart-plot(sec, width, plot-h, label-width: 120pt, column-inset: 100pt, label-gap: 0pt, row-height: none, mark-height: 12pt, group-gap: none) = {
  let spec = sec.chart
  let categories = spec.categories
  let series = spec.series
  let kind = spec.type
  let maximum = spec.scale.max
  let span = maximum - spec.scale.min
  let low = spec.scale.min
  let plot-w = width - label-width
  el("chart-plot", sec.id, {
    if kind == "bar" {
      let groups = ()
      for (i, category) in categories.enumerate() {
        let rows = ()
        for (j, s) in series.enumerate() {
          let value = s.values.at(i, default: 0)
          let row-h = if row-height != none { row-height } else if categories.len() * series.len() <= 8 { 22pt } else { 16pt }
          rows.push(block(height: row-h, grid(columns: (plot-w * (calc.min(0, value) - low) / span, plot-w * calc.abs(value) / span), align: top, gutter: 0pt,
            [],
            el("chart-mark", sec.id, field: "data.series[" + str(j) + "].values[" + str(i) + "]", rect(width: plot-w * calc.abs(value) / span, height: mark-height, fill: chart-role(s.colour.palette, s.colour.index), stroke: none)),
          )))
        }
        groups.push(context {
          // Measure in the label column so wrapped lines belong to the same editable box.
          let label-w = calc.min(label-width, measure(str(category)).width)
          let label-h = measure(block(width: label-w, str(category))).height
          let bars-h = rows.len() * rows.first().height - (rows.first().height - mark-height)
          let label-top = calc.round(calc.max(0pt, (bars-h - label-h) / 2) / 1pt) * 1pt
          let bars-top = calc.round(calc.max(0pt, (label-h - bars-h) / 2) / 1pt) * 1pt
          grid(columns: (label-width, auto), align: top, gutter: 0pt,
            pad(top: label-top, el("chart-label", sec.id, width: label-w, field: "data.categories[" + str(i) + "]", str(category))),
            pad(top: bars-top, stack(dir: ttb, spacing: 0pt, ..rows)),
          )
        })
      }
      stack(dir: ttb, spacing: if group-gap != none { group-gap } else if categories.len() * series.len() <= 8 { 18pt } else { 10pt }, ..groups)
    } else {
      let slot = plot-w / calc.max(1, categories.len())
      let count = calc.max(1, series.len())
      // A group takes 60% of its slot; bars inside it sit 10% of a bar apart, so groups read as groups.
      let group-w = slot * 0.6
      let bar-w = group-w / (count + (count - 1) * 0.1)
      let bar-gap = bar-w * 0.1
      block(width: width, height: plot-h, {
        if kind == "line" {
          let radius = 2.5pt
          for (j, s) in series.enumerate() {
            let ink = chart-role(s.colour.palette, s.colour.index)
            let points = s.values.enumerate().map(((i, value)) => (
              column-inset + (i + 0.5) * slot,
              plot-h * (maximum - value) / span,
            ))
            for i in range(1, points.len()) {
              place(top + left, line(start: points.at(i - 1), end: points.at(i), stroke: (paint: ink, thickness: 1.5pt)))
            }
            for (i, point) in points.enumerate() {
              place(top + left, dx: point.at(0) - radius, dy: point.at(1) - radius,
                el("chart-mark", sec.id, field: "data.series[" + str(j) + "].values[" + str(i) + "]", circle(radius: radius, fill: ink, stroke: none)),
              )
            }
          }
        } else {
          for (i, category) in categories.enumerate() {
            for (j, s) in series.enumerate() {
              let value = s.values.at(i, default: 0)
              let length = plot-h * calc.abs(value) / span
              let offset = plot-h * (maximum - calc.max(0, value)) / span
              let x = column-inset + i * slot + (slot - group-w) / 2 + j * (bar-w + bar-gap)
              place(top + left, dx: x, dy: offset, el("chart-mark", sec.id, field: "data.series[" + str(j) + "].values[" + str(i) + "]", rect(width: bar-w, height: length, fill: chart-role(s.colour.palette, s.colour.index), stroke: none)))
            }
          }
        }
      })
      // Each label stays horizontal while its measured width fits under its group's slot.
      let labels = ()
      for (i, category) in categories.enumerate() {
        labels.push(context {
          let fits = measure(str(category)).width + label-gap <= slot
          let shown = if fits { str(category) } else { rotate(90deg, reflow: true, str(category)) }
          pad(left: (slot - measure(shown).width) / 2, el("chart-label", sec.id, field: "data.categories[" + str(i) + "]", shown))
        })
      }
      pad(left: column-inset, grid(columns: (slot,) * labels.len(), ..labels))
    }
  })
}

#let draw-chart-legend(sec, width: none) = {
  if sec.chart.legend {
    let entries = sec.chart.series.map(s => stack(dir: ltr, spacing: 4pt,
      box(width: 8pt, height: 8pt, fill: chart-role(s.colour.palette, s.colour.index), stroke: none),
      s.name,
    ))
    if width == none {
      el("chart-legend", sec.id, stack(dir: ltr, spacing: 14pt, ..entries))
    } else {
      el("chart-legend", sec.id, width: width, grid(columns: (1fr,) * entries.len(), column-gutter: 8pt, ..entries))
    }
  }
}
