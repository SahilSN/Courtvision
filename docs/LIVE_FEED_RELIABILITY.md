# Feed reliability work — October 26, 2026

## Implemented measurement

`COURTVISION_SCORE_COHERENCE` operator log records public game ID, UTC observation
time, coherent/mismatched acquisition counts, mismatch category (timeline/header
or box points), and elapsed time from first observed mismatch to next observed
fully reconciled acquisition. It runs only inside the single-flight cache owner,
not on cache hits or for every viewer. Repeated episodes are throttled to 60s,
state changes emit immediately, process-local storage is bounded to16 games.
No player names, user/session IDs, raw feeds or raw error messages are logged.
Emitter failure cannot invalidate a coherent snapshot. CLI JSON stays on stdout;
these logs go to stderr, collected by Community Cloud's operator logs.

The interval is an OBSERVED span, not exact upstream latency or proof the source
was continuously wrong. Poll cadence, cache hits, process restarts and evictions
affect it. Acquisition counts are not time-weighted uptime. Existing
COURTVISION_LIVE_STATE logs separately report viewer presentation states/ages.

Summarize an exported operator log without raw payloads:
`python src/summarize_live_reliability.py path/to/operator.log`.
It reports observed episode count/median/p95 and presentation sample counts,
not time-weighted uptime or a release decision. Remove duplicated log-export
lines before comparing runs; incomplete exports and process resets limit inference.

## Viewer states

Successful acquisition stores an explicit UTC verification time. Cache hits,
failed refreshes and retained stale pairs keep the original time; they never
receive a new success timestamp. The main panel shows that timestamp and age
at the last refresh, explicitly not last-play age. Delayed updates identify the
last validated snapshot as NOT current; the expiry caption states estimates are
hidden on refresh beyond the cache's actual retention limit. Paused browsers are
not background monitors and cannot update their visible age without a rerun.
Unavailable hides estimates and tables and explains that verification is pending.

## Recovery policy decision

Do not increase retries, hide mismatches, invent scores or extend stale retention
from a handful of samples. Current15s cache TTL,60s maximum age,15s backoff,
two score-only attempts/.5s pause/8s between-call budget remain unchanged.
The provider's per-request5s timeout is not a hard overall cancellation deadline.
Before tuning, collect full-game episodes, poll-state samples and request counts.
Compare candidate timing against the SAME captured correction/mismatch fixtures;
require identical retained predictions/box frames, expiry and recovery behavior.

## Full-game acceptance run (not yet completed)

Use an explicit reviewed current-day game and private sharing. Start before tip,
keep two real viewer sessions open, opt into refresh, and continue through final.
No new scheduled job is installed by this work. Record:

- Scheduled: no summary/model estimate before tip-off.
- Fresh/delayed/unavailable viewer samples, observed episode durations and ages.
- Forward clock/event movement, stoppages/intermission, final transition.
- Whole-pair score/player reconciliation and bounded request rates under both viewers.
- Last verified timestamps that remain unchanged during failure; expiry removes both panels.
- Recovery restores coherent panels, then removal/expiry/kill pauses requests.

Keep actual provider failures separate from controlled fault/clock tests. Do not
claim a full-game pass from a few late-game samples or an archived simulation.
Use results to set service targets before broadening beyond the private beta;
public/all-game release is not certified by this instrumentation change.
