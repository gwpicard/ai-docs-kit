---
type: regex
target:
  source: file
  path: report.versions/v1/manifest.json
pattern: '"findings"\s*:\s*\{[^{}]*"error"\s*:\s*0\s*[,}]'
---
