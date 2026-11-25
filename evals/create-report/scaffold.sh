#!/usr/bin/env bash
set -euo pipefail

# Synthetic source material only; gathering and drafting belong to the run.
cat > notes.txt <<'EOF'
The trial team tested a collection process over 4 days using 2 collection points.
The trial covered collection and logging, not the later analysis of the readings.
The readers already know the collection process. They need to decide whether
to repeat the trial before extending it.
EOF

cat > results.txt <<'EOF'
The team expected 80 readings and logged 72 readings during the trial.
The remaining 8 readings were missed while the collection points were reset.
The team checked the log at the end of each day. No later analysis was included
in this trial, so the log alone cannot establish the quality of the readings.
EOF

cat > next-steps.txt <<'EOF'
The team proposed repeating the trial over 4 days at the same 2 collection points.
They proposed recording each reset alongside the collection log so that missed
readings can be explained. The decision to repeat the trial is still open.
There is no agreed expansion date or budget in the source material.
EOF
