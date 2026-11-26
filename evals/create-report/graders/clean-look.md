---
type: regex
target:
  source: file
  path: report.versions/v1/manifest.json
pattern: '"look"\s*:\s*\{[^{}]*"clean"\s*:\s*true\b|"look"\s*:\s*\{[^{}]*"tiers"\s*:\s*\{[^{}]*\}[^{}]*"clean"\s*:\s*true\b'
---
Require a look record whose clean flag is true, allowing the tiers object
before the flag as well as the engine's normal serialisation order.
