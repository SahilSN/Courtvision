# Private beta acceptance checkpoint — 2026-10-23

Scope: published Team/Player Intelligence, covered-career summaries, four offline
replays. Live feeds, unrestricted historical analysis, user invitations, and
public exposure remain out of scope.

Automated checks in `src/validate_deployment.py`:

- All eight published Team and Player seasons render.
- Career aggregation and distinct-season comparisons retain player identity.
- Career/season round-trip navigation preserves selection.
- Every curated replay renders at its first/final event; period, turning-point,
  and card callbacks select exact timeline rows.
- Missing replay artifacts show a recoverable error; intelligence remains usable.
- Failed and stale refresh warnings retain the published data.
- Independent sessions retain independent defaults.
- No feed requests or subprocess/worker launches occur in these flows.
- Frozen V7 artifacts still load and infer on CPU; no formula changes.

Local regression suite: 88 tests. These are functional checks, not a performance,
security, accessibility, cross-browser, or load-test certification. Simulated
failure states are not changes to actual published health.

Replay accessibility improvements: chart legend sits above the plot with reserved
axis-title space; solid/dashed named lines supplement color; selected-event score,
play and probabilities appear as text; slider help documents keyboard controls;
turning-point buttons have distinct play-number/clock labels. Automated checks
cover these semantics, chart placement and unchanged plotted values.

Tester feedback is deferred at the user's request; no invitations are sent.
Before widening the beta: check a real screen reader and a second mobile browser, measure
cold/warm load times, and complete the remaining historical player backfill.
Career totals remain covered-archive totals, not complete NBA career totals.
