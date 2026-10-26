# Inactive ESPN traditional box adapter

`cloud_espn_box.normalize_box(event, summary, canonical)` is a network-free,
display-only prototype. No dashboard, provider, historical rating or worker
imports it. Hosted Live remains disabled. It returns player/team DataFrames,
source=ESPN and advancedStatsAvailable=false; it is NOT yet a drop-in replacement
for the existing NBA box-score display contract.

The adapter reuses the strict timeline adapter for event/season/date/home-away
validation and snapshot/header reconciliation, then parses stats by unique
labels, not positional assumptions. Thus it currently requires a play timeline
in the same summary; box-only/pregame snapshots are unavailable. Pure validation
is duplicated if callers independently request both normalized outputs; future
integration should measure and factor that cost without extra HTTP.

Played athletes require exact unique bundled NBA names. Duplicate ESPN/canonical
identities, unknown participants, missing stats, invalid shooting/counts/minutes,
inconsistent player points/rebounds, missing teams or player/team/header point
sum disagreement fail closed. This is not a complete current-player alias service.
Team output currently includes points only; other team aggregate reconciliation
is not claimed. No possessions, ratings, usage, percentages or impact are invented.

DNP rows retain identity/reason with absent numeric stats. Provider minutes retain
their original precision; an explicit didNotPlay=false with MIN=0 remains played.
That display behavior does NOT relax positive-minute historical rating validation.

The compact archived fixture espn_box_0022500001.json records acquisition time
and URL. Tests combine it with the existing same-game timeline fixture, enforce
zero HTTP, reconcile HOU124/OKC125 in double overtime, exercise reordered labels,
bad/missing stats, duplicates, unknown identities, score disagreement and dates.
Historical archive evidence is not a current-live or complete feed certification.

Next: shared raw-cache integration and delayed/partial/corrected feed tests,
broader current-player identities, actual UI contract adaptation, host resource
and stale-state checks before an explicitly approved hosted Live release.
