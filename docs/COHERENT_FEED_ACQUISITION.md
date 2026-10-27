# Bounded coherent feed acquisition

Only a typed ScoreSectionsUnreconciled failure is eligible for one extra loader
call. Each attempt must pass exact identity/date/season validation, timeline/header
score agreement, valid player stats and player/team/header point reconciliation.
Malformed stats, unresolved identities, wrong contexts and transport errors do
not retry. No scores or minutes are repaired, merged, advanced or guessed.

The shared cache's single-flight owner performs at most two attempts, separated
by0.5s. An8s budget is checked between requests and after the pause. Existing
per-request5s socket/2MB/no-redirect bounds remain. This is NOT a hard8s wall-clock
deadline: an already-running socket call is not cancelled. There are no recurring
jobs or unbounded backoff loops. Normal coherent refresh uses one loader call.

Only a wholly validated pair is installed. Exhausted retries retain both previous
panels with the existing stale warning if within max_age; expired/cold data remains
unavailable with no estimate. Existing retry-delay throttling and waiter bounds
remain. Final-game snapshots use the same strict checks, not fabricated100% model
probabilities. Retry constants and typed validators are covered by the deployment
runtime-coherence gate, so stale imported acquisition code cannot approve Live.

Tests cover lag then coherent recovery, exhausted retry/stale/expiry, single-flight
concurrent callers, budget exhaustion, no identity/network retries, final fixture
behavior and coherent stat corrections without mutating prior viewer tables.
Actual source coherence and hosted behavior must still be verified before a
four-game rollout. A bounded retry cannot guarantee a delayed/corrected provider
will publish coherent sections within its window.

## Verification October26

186 full tests passed on Python3.10/3.12; published deployment smoke passed every
season/view/four replays/frozen V7 with zero HTTP/worker calls. A captured real
same-game coherent/conflicting pair replay exercises retry recovery, unchanged
retained tables/predictions, expiry and recovery with controlled time. A separate
ad-hoc AppTest replay timed out; do not count it as a successful new UI visual
check. Existing automated view regressions and deployment smoke passed.

The gate blocked stale acquisition code before HTTP. User explicitly approved
one brief restart if needed; host restarted02:01:55UTC October27. Fresh operator
request coherent-after-reboot-20261027 then reported runtimeReady=true:
MIN@CLE548states(post) and IND@MIL418states(in) passed with one attempt. DAL@MIA
exhausted exactly two attempts and remained unavailable. CHI@BOS stopped after
one attempt; independent inspection found newly participating Chris Cenac Jr.
on BOS1610612738 has no reviewed mapping. No identity was guessed or retried.

The four-game hosted rollout therefore remains unapproved and Live stays off.
Temporary diagnostic removed. Next requirements are independent verification of
the new participating identity and coherent DAL feed sections, followed by actual
hosted view/refresh/rollback checks. No claim that bounded retries fix every
upstream correction, or that completed-game evidence proves four advancing feeds.
