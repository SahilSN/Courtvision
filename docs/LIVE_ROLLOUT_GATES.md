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

The UI remains the gated archived local preview; real refresh controls and
private Live rollout are withheld pending broader active-feed/concurrency checks.
The actual host archived workload gate passed, but that alone is not a safe
rollout certificate. Do not reactivate the old request, weaken identity checks,
or describe sequential archived runs as concurrent/current-feed testing.
