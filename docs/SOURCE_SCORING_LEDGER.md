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
