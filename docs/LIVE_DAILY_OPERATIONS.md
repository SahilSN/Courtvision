# Owner-only daily Live beta — deployment and operation

This is a bounded private trial, not a public/all-game production release.
The owner authorized automatic daily preparation and game-window testing over
the next few days. The initial policy expires **October30,2026,03:00 Pacific**.
Changing or renewing that policy is an explicit operator decision, not something
the nightly job does indefinitely. Host private authentication remains required.

## What runs automatically

The EXISTING Mac nightly job (01:00 local time, with its existing login/wake
catch-up behavior) still updates team/player intelligence and prior-results
coverage. After valid dated context is built, it now prepares:

- An exact dated slate, earliest scheduled games first, at most FOUR games.
  Larger days explicitly report deferred games; capacity was not increased.
- Official NBA CommonTeamRoster identities for at most eight selected teams.
  Exact team/season/player IDs and names only; no ESPN-ID conversion or fuzzy
  resolution. Data updates can be read without restarting Python.
- A deduplicated unresolved/conflicting identity review queue from a bounded
  summary inspection of those games. This is a nightly observation, NOT a full
  roster-completeness guarantee or continuous detection of late participants.
- A daily manifest bound to the EXACT context digest, expiring within24hours
  and no later than06:00Eastern after its scheduled date.

At most eight official roster plus four ESPN summary requests are attempted,
with5s per-request/2MB/no-redirect limits and a65s BETWEEN-CALL preparation budget.
This is not hard cancellation of an in-flight HTTP request. No model runs here.
No extra scheduled jobs, hourly workers, database, paid provider or account was
created. Nightly publication copies only the expanded data allowlist from an
isolated clone; the user's index and active datasets are never staged.

The dashboard reads bounded local artifacts only. Opening it cannot start the
nightly job, refresh official rosters, publish to GitHub or launch subprocesses.
It offers prepared MATCHUPS, not pre-certified predictions. Scheduled games
still have no estimate. Every in-game estimate still requires the existing
exact event/date/team/player and whole-pair score checks and frozen V7 pipeline.
Stale retention/expiry, independent host opt-in and kill controls are unchanged.

## Activation and pause precedence

1. Host opt-in is required; the host kill switch wins immediately on refresh.
2. A valid explicit `cloud/live_rollout.json` window wins over the daily slate.
3. A disabled or corrupt manual file pauses Live. Only a valid EXPIRED manual
   window may hand over to daily operation. Removing a manual window is not a
   universal kill if daily operation is enabled.
4. Automatic operation also requires enabled/unexpired
   `cloud/live_daily_policy.json`, a matching/unexpired daily manifest and fully
   revalidated context. The policy is capped at four games and seven days.
5. Missing/mixed/stale files or a replaced context digest fail closed. Neither
   a newer season nor another day's pregame records can substitute.

For an immediate repo-controlled pause, set `cloud/live_rollout.json` to
`{"enabled":false}` and publish it. This latch is NOT overwritten by nightly
publication. Alternatively use `COURTVISION_DISABLE_LIVE_BETA=1` at the host.
Verify an existing auto-refresh session pauses on its next refresh. No runtime
code hot-reloading is attempted. Code changes still require coherence checks
and, when needed, an operator-approved restart.

## Identity failures are explicit, not guessed

An official roster may supplement the pinned static index for the EXACT current
game date/season/team only. It cannot modify historical/replay identity behavior.
Official and reviewed IDs that conflict remain ambiguous and block analysis.
Old, missing, malformed, future-timestamped or unavailable roster artifacts add
no identities. Existing explicitly reviewed mappings remain usable.

An actual October26 Mac rehearsal found NBA roster requests timing out, including
the NBA client's ordinary headers. The complete isolated rehearsal prepared four
matchups, deferred five, reported eight unavailable roster teams and six pending
identity reviews. It correctly reported DEGRADED, not successful automatic roster
coverage. No active artifact was replaced/published by this rehearsal. Automatic
sync is implemented but upstream availability remains an operational limitation;
unresolved players need independently verified official evidence or a later
successful sync. Do not relax identity checks to compensate.

Summary inspections can also be unavailable before lineups are published.
Nightly preparation problems do not discard successfully refreshed intelligence
or mark a blocked feed valid. They are reported separately in nightly status and
logs; old artifacts never receive a fresh successful timestamp.

## Health, release identification and rollback

See [deployment recovery](DEPLOYMENT_RECOVERY.md) for the always-available
sidebar Update health panel, separate published intelligence/local nightly
evidence, independent switches and scoped code rollback checklist.

The Live view's collapsed **Data readiness** section exposes preparation date,
expiry, prepared/deferred counts and degraded roster/review status. The release
label `owner-beta-daily-v1` identifies this implementation, not a cryptographic
deployed commit or proof of provider health.

`PYTHONPATH=src .venv/bin/python src/live_operations.py` emits a sanitized,
read-only status report. Nonzero exit means preparation is not fully prepared.
It deliberately distinguishes matchup activation from artifact readiness and
does not claim provider uptime, advancing clocks, model/runtime readiness or
release certification. The Mac's rotating nightly logs/status remain persistent;
Community Cloud's existing acquisition/coherence logs remain operator evidence.
An always-on remote metrics store and push-alert service are NOT installed.

Check `results/live_context/*_identity_review_v1.json` for the owner review queue.
Review public names/team scopes against official sources before adding mappings;
do not guess IDs or treat an empty pregame queue as complete roster certification.

For a code rollback, first pause Live, then deploy a reviewed known-good code
revision through the clean latest-main release checkout, preserving newer data.
Do not force-push main or roll back nightly/backfill datasets. Restart if the
runtime coherence gate requires it, then verify the default dashboard and the
explicit private activation separately.

## Remaining launch work

### Game-state presentation

The compact Game Center puts the scoreboard and solid probability lines ahead
of readiness/debug information. States are Scheduled, Live, Delayed, Unavailable
and Final; ambiguous source metadata remains labeled Snapshot. Final requires
BOTH the accepted scoreboard and summary to explicitly say post/completed=true.
A zero clock, a lead or one source's final flag is never enough. State metadata
travels with the accepted cached pair, so a failed refresh cannot label retained
old scores as a newly confirmed final. Delayed/uncertain refresh state takes
precedence over a retained final marker. Final probabilities remain unchanged
model history and are labeled as such, not forced to100percent.

The existing October27 hourly checks are SPOT CHECKS, not a full-game monitor.
Use actual game windows over the next few days to verify first nightly
publication, roster-source access, late participants, corrections, retention,
expiry, overnight/final transitions and recovery. A full-game/two-viewer run,
broader capacity, persistent host metrics/alerts, major UI polish and moving
updates off the Mac remain separate work. No unrestricted daily coverage or
public-scale certificate is claimed by this deployment.
