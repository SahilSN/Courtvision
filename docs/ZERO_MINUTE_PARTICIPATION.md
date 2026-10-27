# Reported-zero-minute historical appearances

Game 0022400942 (Indiana–Milwaukee, March 11, 2025) contains Tony Bradley's
rebound at Q2 0.2 seconds. The cached traditional box reports 0:00 minutes,
one defensive rebound; the advanced box reports one possession. His existing
frozen WPA summary records one event, net WPA about 0.021469. These agree on
player 1628396 and team IND. The old positive-minutes-only filter dropped his
row and correctly failed the subsequent impact conservation check.

The dataset join now retains an explicit zero-duration box appearance only if
it also has positive possessions, a recorded box action, and a positive event
count for the exact player/team in the WPA summary. Blank/missing durations,
wrong teams, and unsupported zero-minute entries still fail reconciliation.
Source minutes remain zero: no seconds are inferred or fabricated. Published
dataset validation permits zero minutes only with positive possessions and
attributed events; negative/missing minutes remain invalid. All WPA columns and
event counts must still reconcile. No model, attribution, or rating formula
changes are involved.

Regression tests cover the corroborated case and missing minutes, wrong teams,
missing possessions/activity, and unsupported published zero-minute rows.
The actual cached game passes the unchanged source validation with 20 player
appearances and zero change to total attributed WPA.
