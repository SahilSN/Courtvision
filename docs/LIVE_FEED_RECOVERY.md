# October 26 live-feed corrections and recovery evidence

Hosted Live remains default-off; no activation or host setting changes accompany
this patch. Frozen V7, historical/replay adapters and nightly jobs are unchanged.

## Scoped corrections

- In-progress ESPN traditional-box MIN `-`/`--` is missing display data, not zero
  or DNP. Preserve it as null with minutesAvailable=false. Other malformed minutes,
  missing plus/minus, numeric counts, identities and score reconciliation still
  fail. Pregame/completed/unknown-status placeholders are rejected as before.
- Christian Anderson NBA1643515 / CHA1610612766 and Meleek Thomas NBA1643509 /
  CLE1610612739 are exact 2026–27/team-scoped reviewed additions. Sources:
  https://www.nba.com/player/1643515/christian-anderson and
  https://www.nba.com/player/1643509/meleek-thomas/profile (reviewed October26).
  The live stats API returned unusable data and CDN403; official NBA profiles,
  not ESPN numeric IDs or guessed mappings, independently establish identities.

## Actual current-feed evidence

NBA0022600119/ESPN401909868 WAS@CHA and NBA0022600120/ESPN401909869 MIN@CLE:

- At23:26:21UTC both jointly coherent: CHA15–WAS13 and CLE11–MIN23.
- At23:26:37UTC both remained coherent (unchanged is not advancement evidence).
- At23:26:55UTC headers advanced to15–15 and13–23 while play timelines lagged.
  Strict validation rejected both updates; shared caches retained the previous
  coherent score/probability/box pair and reported stale_snapshot. No panel mixed
  old/new values. This is observed real acquisition/retention, not a synthetic fault.
- A later bounded check validated both newer coherent pairs: WAS@CHA85states,
  Q1 2:53,15–15; MIN@CLE81states,Q1 3:39,13–23. Frozen probabilities finite/in-range.
  This confirms subsequent coherence/advancement, not an unlimited reliability claim.
- Replaying captured valid/invalid source pairs through the real join and local
  Streamlit AppTest passed stale-warning/two-table retention, expired unavailable
  with no estimate/tables, and recovery after retry backoff. Expiry/recovery use
  a controlled cache clock and previously captured coherent payload: not a claim
  of a real observed outage duration or browser-level recovery.

## Validation / remaining release boundary

175 full tests passed on Python3.10 and3.12 before two additional boundary tests;
the final focused box/identity suite covers those as well. Deployment smoke
passed all eight seasons/team/player/careers/four replays/frozen V7, with zero
HTTP/worker launches. Source compilation and diff whitespace checks are required
before publication. Local diagnostic artifacts are under /tmp/courtvision-*
and are not published datasets.

Before activation verify the deployed current-feed UI and host settings/private
access, then use only the existing short-lived allowlist + independent host
opt-in. Do not weaken score reconciliation, add an automatic polling job, or
describe default-off code publication as enabling hosted Live.
