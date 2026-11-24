---
type: regex
target:
  source: file
  path: report.md
flags: m
pattern: '(?:^:::[ \t]+\{#[^\r\n}]+\.section\b[^\r\n]*\}\r?\n(?:(?!^:::[ \t]*\r?$)[\s\S])*?^(?![ \t]*[#>:])[ \t]*[^\r\n]*[A-Za-z][^\r\n]*[ \t]+\[S\d+[^\]\r\n]*\](?:(?!^:::[ \t]*\r?$)[\s\S])*?^:::[ \t]*\r?$[\s\S]*?){3}'
---
Require at least three section blocks containing drafted text and
an inline citation. Source-list entries and empty outline blocks do not count.
