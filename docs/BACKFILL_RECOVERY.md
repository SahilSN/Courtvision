# Historical backfill recovery — October 26, 2026

NBA game0022400942 remains incomplete: Tony Bradley (1628396, IND) has an
attributed rebound/WPA event and one box-score possession, but both the cached
and freshly requested NBA traditional box scores report minutes=0:00. The
positive-minute participant validation correctly rejects this conflict. No
minutes, impact or model values were fabricated and no validation was relaxed.

Two workflow fixes prevent the unresolved source game from halting all history:

- The runner cycles through incomplete seasons instead of always selecting the
  newest one. Failed games remain pending and are retried on subsequent cycles;
  no season is declared complete while a game is missing.
- On a season batch with no progress, the milestone publisher flushes any new
  validated partial checkpoint below the usual 500-game threshold. Publication
  still validates both CSVs, reconstructs ratings, preserves published rows and
  uses the existing isolated non-force Git push. Existing upload backoff remains.

This allows 1,229 locally processed 2024–25 games to publish despite the last
game, while older-season processing can continue. Previously only1,039 games
were public because the remaining190 fell below the next milestone.

The worker must restart to load these changes. Graceful interruption preserves
checkpoints; no concurrent manual backfill worker should be started. Source
reconciliation for the single zero-minute appearance remains open.
