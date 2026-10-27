# Limited private Live beta — release evidence, October 26, 2026

Status: ready for an explicitly dated, operator-controlled private beta, not
unrestricted public/all-game release. Default-off is preserved after validation.

## Final fixes and checks

- Independently verified official profiles: Zuby Ejiofor ATL1610612737,
  NBA1643544 (https://www.nba.com/player/1643544); Bruce Thornton HOU1610612745,
  NBA1643570 (https://www.nba.com/player/1643570/bruce-thornton). Exact season/team
  mappings only; no guessed IDs, fuzzy matching or model changes.
- 199 regressions passed on Python3.10 and3.12. The clean published checkout
  also passed 199 tests and deployment smoke on Python3.12 with the concurrently
  published historical data retained. All eight published seasons, careers,
  four curated replays and frozen V7/scaler CPU inference passed.
- One user-approved restart loaded the final identity code at
  03:10:23.893 UTC October27 (8:10 p.m. Pacific October26). No second restart.
- Actual hosted MEM@UTA0022600126 observations progressed from438 to440 states,
  elapsed2438 to2452, actions439 to441. GSW@DEN was coherent at halftime, not
  counted as progression. These are separate per-game evidence, not an all-game
  certificate; the initial aggregate request remained not_ready.

## Retention, expiry and recovery

Owner request release-retention-20261027-0316 reported controlledRecovery=passed:
unchanged predictions and both box panels retained with explicit stale state,
expired data unavailable at61s, recovery after backoff. It uses the exact
accepted public feed, controlled clock/timeouts, and unchanged frozen artifacts.
No faults are injected into viewers. This is NOT an actual provider-outage test.

Earlier recovery test setup fetched a new asynchronous pair and failed; it was
not accepted. The final helper retains an immutable copy only after the complete
join succeeds, never overwriting it with an invalid/stale refresh. Regression
tests cover that distinction. Retention evidence is independent from clock
progression and never makes canEnableLive true.

## Two actual hosted viewers

After the above backend evidence, a15-minute one-game private validation window
was opened. Two independent Streamlit browser sessions initially showed
unavailable, with no estimate. Concurrent manual refreshes recovered both to
MEM102–UTA101, Q43:37, identical predictions, solid charts and player tables.
Both15-second switches were then enabled; both advanced automatically to Q43:19
with matching81.3%/18.7% predictions. This is two same-game browser sessions,
NOT four-game load or public capacity certification. Prior archived four-caller
CPU evidence remains separately documented.

## Operational boundary

Temporary diagnostic and Live activation files are removed after validation.
Verify existing sessions pause and default navigation recovers on reload.
Private sharing, independent host opt-in, runtime coherence, dated context,
expiry/kill, strict joint validation and bounded stale retention remain required.
No new schedules, model changes, backfill resets or nightly-job changes.

A release operator must select only reviewed games with fresh context and source
verification and use a short dated window. Unknown players/incoherent feeds
remain unavailable, not zeros or guessed estimates. Automatic daily activation,
unrestricted coverage and public-scale deployment are not approved by this signoff.
