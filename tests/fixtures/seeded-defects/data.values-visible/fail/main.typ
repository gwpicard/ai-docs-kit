#import "/lib/theme.typ": colour, page-setup
#import "/components/table.typ": table

#show: page-setup.with("slides")
#set text(fill: colour("ink"))

#let comp = json("/composition.json")
#let sec = comp.sections.at(0).props + comp.sections.at(0).content
#table(sec + (data: (columns: sec.data.columns, rows: sec.data.rows.slice(0, 2))))
