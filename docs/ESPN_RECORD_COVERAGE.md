# Nightly prior-result cross-check

The Mac's existing locked nightly job now runs `espn_record_coverage.refresh_coverage`
after the team/player refresh and before its isolated Git publication. No new
scheduler or hosted Live activation is introduced. Existing frozen models,
rating formulas, replay and live providers are unchanged.

The check reads the ESPN daily scoreboard for every calendar day from the
provider's declared season start through yesterday in America/New_York. It does
not assume a date-range request is complete or skip days with no events. Each
request has a five-second socket timeout, no redirects/retries and a 2MB decoded
body cap; the loop has a 90-second budget checked between requests. Socket
timeouts are not a hard whole-operation cancellation deadline. Later-season
refreshes can exceed the budget and fail safely; verified daily caching is a
future optimization, not currently implemented.

Only explicitly regular-season events are matched. Prior games must be final;
date, exact team names, home/away, final margin and both win/loss outcomes must
agree with independently published NBA history. Duplicate, unknown, unfinished,
missing or extra games refuse a new artifact. NBA game IDs come from that history
only, never an ESPN-ID cast or guessed sequence. ESPN abbreviations such as NY,
SA and GS are not used as NBA identities.

Output: `results/live_context/<season>_coverage_v1.json`, schemaVersion1,
scope `prior-results-cross-check`, explicit completeThrough/checkedAt/checkedDays
and matched canonical/ESPN IDs with final scores. This is evidence of agreement
between two sources, NOT mathematical proof both sources cannot omit the same
game, a full future schedule, or a hosted pregame context. No consumer should
treat its watermark as current for a later date.

On source or reconciliation failure, the previous file is retained. The nightly
runtime status records recordCoverage=failed and the overall run is incomplete,
but normal team/player publication still proceeds. Coverage regression is
rejected both locally and during isolated publication. The allowlist adds only
this season's coverage JSON. Standard nightly catch-up behavior is unchanged.

## Actual source check

On October23,2026 (Pacific), requests for every day September30–October22
completed successfully. All16 prior regular-season games matched the local
NBA-derived history, including both sides' outcomes and margins. The resulting
artifact carries its own UTC checkedAt. This proves that bounded historical
window worked, not future source availability or actual hosted Live readiness.

Remaining: verified NBA-ID mapping for today's games, strict dated context reader,
native ESPN box scores, broader captured-feed and cache integration tests, and
whole-pipeline host resource validation. The earlier offline full-season
publication contract remains separate/inactive; this check does not falsely
attest full-season coverage to it.
