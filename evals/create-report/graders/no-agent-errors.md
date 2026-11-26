---
type: regex
target:
  source: file
  path: report.versions/v1/manifest.json
pattern: '"severity"\s*:\s*"error"'
match: not_contains
---
