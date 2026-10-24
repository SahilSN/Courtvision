# Daily canonical identities and dated pregame context

The nightly context step now follows the prior-result cross-check with one NBA
ScoreboardV3 request (8s timeout) and one bounded ESPN daily request. Exact Eastern
date, regular-season/year, home/away team names and the full daily matchup set
must agree. NBA IDs come from ScoreboardV3 only, never guessed from ESPN IDs.
If the existing NBA catalog helper filters out an incomplete game, set equality
with ESPN refuses publication rather than silently hiding it.

`results/live_context/<season>_day_context_v1.json` carries explicit gameDate,
completeThrough, checkedAt, coverageCheckedAt, canonical games, ESPN IDs and
pregame contexts. Prior coverage must end exactly the day before; checkedDays
must be contiguous. Prior scores reconstruct raw records, using unchanged
current-season smoothing. Today's scores/outcomes never enter pregame context.

`daily_live_context.read_day_context(path, canonical)` is offline and validates
the requested date/season/game/team identity, coverage date and raw-record/rate
consistency. Missing, corrupt, stale or mismatched data raises unavailable; no
neutral fallback is used. The artifact is trusted deployment data, not signed
third-party input. An explicit historical canonical request can read its dated
file; the caller must supply today's date for Live. No app imports this reader
yet, and hosted Live remains disabled.

Atomic replacement retains the prior daily file if refresh fails; dated readers
then reject it for newer games. The existing nightly lock owns serialization.
Nightly status records failure and still attempts team/player publication.
Publication rejects date regression and uses the isolated Git allowlist. Same
nightly schedule and catch-up rules; no intraday refresh added.

Actual source validation October23,2026: all12 daily NBA games matched ESPN,
with prior contexts built from the16 cross-checked games through October22.
The checkedAt values in the published evidence files record acquisition time.
This is Mac-side validation, not proof NBA discovery is reachable from Cloud;
the intended hosted reader needs no discovery HTTP. No full-season completeness
claim is made. Known prior-source/common-omission limits remain documented in
ESPN_RECORD_COVERAGE.md. Date-only pregame cutoffs retain existing behavior.

Remaining gates: reviewed player identity exceptions, native ESPN box-score
adapter, more feed/cache integration fixtures and actual-host resource/stale
messaging checks before an explicitly approved hosted Live release.
