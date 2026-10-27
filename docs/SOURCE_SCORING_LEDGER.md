# Strict scoring-event reconciliation

The October 26 Dallas–Miami ESPN feed ended with a 109–113 header and
112–113 cumulative play scores. Play 401909871472 was a personal foul,
explicitly `scoringPlay: false`, but its cumulative home score added three.
This persisted to the final play; retry alone could not resolve it.

Only when cumulative scores disagree with the header, the live adapter can use
explicit scoring events. Every play must carry an explicit scoring flag; made
events require an exact reviewed player/team, a made-shot/free-throw type and
integer scoreValue of 1, 2 or 3. The resulting ledger must agree with every
individual scorer, both player sums, both team totals and the header. Missing,
ambiguous or contradictory evidence still fails closed. Full traditional box
validation remains mandatory. Raw cumulative scores are retained in
reportedScoreHome/reportedScoreAway and the UI identifies ledger provenance.

The captured public fixture reproduces the phantom foul points and verifies
109–113 without mutating the payload. Regression cases reject missing flags,
invalid points, falsely flagged fouls, mismatched headers/player totals and
unknown identities. Coherent feeds retain their original path. This changes
neither frozen V7/scaler parameters nor historical/replay parsing.

The Boston exact-name mapping adds Chris Cenac Jr., NBA 1643416, only for Boston
1610612738 in 2026–27. Official identity: https://www.nba.com/player/1643416/chris-cenac-jr.

Validation before publication: 190 tests passed on Python 3.10 and 3.12.
Hosted validation and any temporary rollout are separate release evidence;
these unit tests do not certify four simultaneously advancing feeds.

The approved single restart loaded the fixes at 02:18:13 UTC October 27
(7:18 p.m. Pacific October 26). Actual Community Cloud diagnostic
`ledger-after-reboot-20261027-0218` reported runtimeReady=true. Boston passed
550 states, Dallas 490, Minnesota 552, each on its first acquisition. These
three games were completed. Indiana exhausted two attempts during a section
mismatch; a separate public snapshot showed header 108–100 versus play 105–100.
No four-game activation was authorized by that failed diagnostic.

The final bounded request `ledger-final-check-20261027-0220` passed all four
on actual Community Cloud, runtimeReady=true, one acquisition each:
Boston 550, Dallas 490, Indiana 491 (in progress), Minnesota 552 states.
This established four-game pipeline coverage, not four simultaneous advancing
feeds. Only then was a 15-minute private four-game UI validation window opened.

Actual hosted browser checks rendered all four game selections, score cards,
solid-line charts and traditional player tables. Boston showed 134–99; Dallas
113–109 with the explicit-ledger provenance caption; Indiana 101–108 at Q4
1:15; Minnesota 125–127 after overtime. Manual refresh was exercised. Indiana's
15-second switch was enabled then paused; no advancing-clock certificate is
claimed (the observed clock remained 1:15). Frozen snapshot probabilities were
not overridden at completed-game boundaries. Temporary rollout and diagnostic
requests were removed after validation. Private sharing, nightly jobs and active
backfill datasets were not changed.
