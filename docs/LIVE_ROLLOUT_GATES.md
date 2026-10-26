# Live rollout attempt — October26,2026

Live has NOT been enabled. The following evidence is separate, not interchangeable:

- The new fixed-size operator pipeline diagnostic passes locally. It loads frozen
  CPU artifacts once, runs the archived594-state pipeline three times (one cold,
  two warm), and reports whole-process peak RSS and timings. It performs no HTTP.
  Pass thresholds are model load<30s, each analysis<10s and peak RSS<900MiB.
  This is not a concurrency test or hard execution-time cancellation mechanism.
- Host requests now explicitly select kind=access(default) or kind=pipeline.
  Unknown kinds are refused. Existing15-minute expiry, exclusive claim-before-run,
  sanitized logs and once-per-container rules remain. No viewer control or timer
  starts the workload. Failed claims do not retry on reruns.
- A short-lived pipeline request was deployed. The existing private app was
  asleep; its wake control was used, but the app/log view remained loading.
  Browser diagnostics initially showed HTTP400 health checks and exhausted log
  reconnects (also visible before diagnostic deployment). A subsequent page reload
  recovered the connection and owner logs confirmed the actual diagnostic result:
  pipeline_baseline_passed, environment=community-cloud, Python3.12.15,
  modelLoadSeconds2.1592, analyses0.7993/0.5821/0.3241seconds, processPeakMiB438.7,
  594states, requestId pipeline-20261026-180549. Startup log timestamp18:06:48UTC.
  No reboot or sharing change was made. Activation was removed afterward.
- Real recent ESPN regulation feeds for NBA0022600112 and0022600113 initially
  failed closed on missing rookie identities. NBA BoxScoreTraditionalV3 confirmed
  Darryn Peterson1643408/UTA, Chaney Johnson1643052/BKN and Joshua Jefferson1643538/BKN.
  Exact name additions in reviewed_live_players.py are scoped to2026–27/team and
  record the canonical source games. No fuzzy match, guessed ID, global roster
  update or model change is used. Unknown names still block analysis.
- Both games then passed timeline and traditional-box reconciliation:513/505
  states,31/27 roster rows,4 periods each. Compact dated source fixtures preserve
  the evidence with offline regression tests. These completed recent games are
  not a claim that today's future/in-progress games all work or that every
  legitimate correction/current identity is covered.

At that stage the UI remained the gated archived local preview; hosted refresh
controls and private Live rollout were withheld pending further checks.
The actual host archived workload gate passed, but that alone is not a safe
rollout certificate. Do not reactivate the old request, weaken identity checks,
or describe sequential archived runs as concurrent/current-feed testing.

## Subsequent two-caller check and local real refresh

A hot-deployment check initially ran the previous imported probe implementation;
its report contained no concurrency fields and was NOT accepted as concurrency
evidence. The operator runner now loads the fixed reviewed probe path fresh.
A new expiring request then reported actual Community Cloud two-caller success:
requestId pipeline-fresh-20261026-181958, Python3.12.15, model load0.0042s,
sequential analyses0.7361/0.3725/0.3589s, two concurrent calls0.7982s total,
process peak486.6MiB,594states each. This checks shared-model/cache CPU calls,
not a browser/HTTP load test. Activation was removed after verification.

The loopback local preview now has an explicit Today/local-check source, two
verified games maximum. Archived remains the default. Real refresh is manual
by default, with opt-in15s fragment refresh. Context is validated before HTTP;
the scoreboard is cached15s and a jointly validated shared snapshot supplies both
panels. Only the cache owner fetches the summary; each response uses existing5s
timeout/2MB/no-redirect limits. Pregame skips summary/model and shows no estimate.
Missing/incoherent context or feed is unavailable, with bounded stale fallback
through the existing cache. This code has NO route in cloud/app.py yet.

Automated source tests cover two-request pairing, pregame summary suppression,
wrong date/season/missing/duplicate event rejection. AppTest covers scheduled UI,
auto-refresh off, no model/no estimates. A coherent synthetic stat correction
replaces a cached pair without mutating a previous viewer's tables. No fabricated
score correction is represented as source evidence.

Release is not complete: at the actual check all9October26 games were pregame;
first tip-off23:00UTC (4p.m. America/Los_Angeles). An advancing live feed and its
real refresh/stale UI still require game-window verification. A safety review
refused adding the hosted route before those prerequisites; no workaround,
hosted-navigation change or sharing change was made. Do not bypass that gate.
