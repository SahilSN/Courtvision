# Deployment readiness — October 26, 2026

The private Intelligence deployment includes complete 2024–25 player coverage.
Live remains default-off; this work did not add daily automatic activation,
unrestricted discovery, a scheduler or sharing changes.

## Published work

- Added the bounded two-round current-feed diagnostic described in
  LIVE_RELEASE_PROCESS.md, including the existing expiring owner-only runner.
- Exact official NBA profiles verified six season/team identities: Kingston
  Flemings (ATL1643412), Cameron Boozer (MEM1643409), Yaxel Lendeborg
  (GSW1642865), Brandon Williams (GSW1630314), Bryce Hopkins (DEN1643624),
  Trevon Brazile (DEN1642350). Source URLs are retained in reviewed_live_players.
  The exact GSW scope resolves Williams's retired namesake; ambiguity remains
  outside that scope and for conflicting reviewed IDs.
- 197 tests passed on Python3.10 and3.12; deployment smoke passed all published
  seasons, careers, curated replays and unchanged frozen CPU inference. The
  actual clean publishing clone passed 14 focused tests. Diff checks passed.

## Observed current feeds

Initial local rounds rejected all three candidates for missing identities.
After the reviewed additions, all three normalized/box/model pipelines passed
at least once. A later Utah feed mismatch retained a marked stale pair, rather
than installing inconsistent panels. Unchanged observations did not pass the
progression gate.

The user approved one hosted restart after tests. Actual host startup was
02:57:32.822 UTC October27 (7:57 p.m. Pacific October26). Request
late-progression-20261027-0257 on Community Cloud reported not_ready:

- MEM@UTA: two validated observations, 382 states, same Q3-end clock, 76–89.
- GSW@DEN: validated172 states then stale172 after two failed score retries;
  the prior coherent47–44 pair was retained.
- ATL@HOU: unavailable in both rounds. Independent current source inspection
  found newly participating Zuby Ejiofor (ATL) and Bruce Thornton (HOU) without
  exact reviewed mappings. These are not verified NBA IDs and were not guessed.

This is actual hosted rejection/stale evidence, not an advancing-feed or
recovery certificate. No Live allowlist was created. Existing four-game archived
CPU and earlier hosted UI results remain separate from these current checks.

The final bounded request late-final-progression-20261027-0300 reported:

- MEM@UTA validated382 ->384 states, action383 ->385 at elapsed2160.0,
  76–89: event progression, not an advancing-clock claim.
- GSW@DEN unavailable after two score retries, then recovered to a validated
  185-state52–52 snapshot at elapsed1220.0 on its next acquisition. This is
  actual unavailable-to-valid recovery in one cache, not stale-to-valid proof.

The aggregate remained not_ready because GSW did not supply two consecutive
valid observations. Live stays off. The temporary operator request was removed;
no additional monitoring job or restart was scheduled. Remaining release work:
review the two newly involved ATL/HOU identities, obtain sustained coherent
progression and hosted viewer/failure-recovery evidence, then a dated private
activation decision. Do not convert isolated successes into unrestricted release.
