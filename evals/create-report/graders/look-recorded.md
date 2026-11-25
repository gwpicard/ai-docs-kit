---
type: regex
target:
  source: file
  path: report.versions/v1/manifest.json
pattern: '"agent"\s*:\s*\['
---
The build's automatic look alone is insufficient: the look agent must record
its findings, including an empty array when no fault was found.
