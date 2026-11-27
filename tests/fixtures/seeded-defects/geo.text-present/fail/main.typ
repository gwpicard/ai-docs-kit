// Seeded defect: draw the list and heading but silently omit its prose.
#import "/lib/theme.typ": colour, page-setup
#import "/components/bullet-list.typ": bullet-list

#show: page-setup.with("doc")
#set text(fill: colour("ink"))

#let comp = json("/composition.json")
#let sec = comp.sections.at(0).props + comp.sections.at(0).content
#bullet-list(sec + (content_order: ("items[0]", "items[1]")))
