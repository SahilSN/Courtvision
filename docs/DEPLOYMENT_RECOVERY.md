# Private beta: update health and safe recovery

## Read evidence before acting

The sidebar **Update health** is available in both Intelligence and Live,
including when Live is disabled. It only reads bounded artifacts and sanitized
process-local feed observations. It cannot run jobs, publish data, edit identity
mappings, expose logs, or enable Live. It is suitable for the current owner-only
app, not a substitute for owner authorization if sharing is expanded later.

Team and player refreshes are shown separately. A successful check older than
36 hours is **stale**, not current. Invalid, future or timezone-free timestamps,
contradictory successful counts, missing/wrong-season files are unavailable.
Games-through means latest included game date; it is not a freshness timestamp.
No games on a night can still produce a fresh successful check. A published
refresh record is not proof that the Mac is online or that a future job succeeds.

Live preparation is separate: prepared matchups are not certified feeds or
validated player completeness. Pending identity counts and deferred coverage are
shown. Recent feed observations are from this host process, at page load, within
two minutes only. No observation means unknown, not an outage. Reload the page
to update the sidebar; game-fragment refreshes do not rerender the sidebar.
Process observations reset on restart and are not durable uptime measurements.

## Owner checklist

1. On the Mac, run the existing read-only health command from the repo:
   `PYTHONPATH=src .venv/bin/python src/live_operations.py`.
   It now includes separate intelligence and saved local nightly-attempt status.
   Its exit code still reports Live preparation, not overall intelligence health.
2. Inspect `results/.runtime/nightly/status.json` and the rotating `updates.log`
   locally for the latest attempt and publication outcome. Raw errors are not
   copied into the hosted health panel. A saved “running” record is not proof
   the process is alive; check the actual job before starting another run.
3. Check the existing Mac LaunchAgent, `com.courtvision.nightly-intelligence`.
   It must point at the repo's `.venv/bin/python`, run `--scheduled`, retain the
   1 a.m. local schedule and login/wake catch-up. Do not add a second scheduler.
4. Failed or incomplete refresh: inspect source access and pending games. Retain
   validated datasets; do not rewrite timestamps or delete saved progress.
   After fixing a concrete cause, a manual `--scheduled` invocation of
   `src/run_nightly_intelligence.py` uses the existing lock and due check.
   This is an operator action, never a viewer-page action. Publication failures
   remain visible locally; absent new hosted evidence is stale/unknown, not a
   claimed successful upload. The next scheduled invocation retries failed work.
5. Identity problems: review the dated `*_identity_review_v1.json` against
   official team/player evidence. Never guess IDs, lower matching standards or
   bypass whole-pair validation to increase game coverage.

Saved nightly status is read with a size bound. Malformed JSON, invalid dates,
naive timestamps or a future “success” cannot suppress catch-up. Both team AND
player pipelines must report success; missing pipeline evidence is incomplete.
No extra job or automatic retry loop has been introduced.

## Independent feature controls

| Control | Effect |
| --- | --- |
| Host `COURTVISION_CLOUD_READY` absent/not `1` | Staging only; no dashboard data |
| Host `COURTVISION_DISABLE_LIVE_BETA=1` | Pause Live regardless of other policies |
| Host `COURTVISION_ENABLE_LIVE_BETA` absent/not `1` | No Live opt-in |
| Repo `cloud/live_rollout.json` with `{"enabled":false}` | Explicit manual pause; nightly does not overwrite it |
| Disabled/expired `cloud/live_daily_policy.json` | No automatic daily activation; a still-valid explicit manual window is separate |
| Host `COURTVISION_DISABLE_OPERATOR_PROBES=1` | Optional operator probes off, independent of ordinary dashboard |

Private sharing/authentication must remain enabled at the host; none of these
flags replaces access control. Removing a manual window alone is NOT a kill
while the daily policy is eligible. Every fragment refresh rechecks guards.
Changing host settings can restart the app; obtain approval for a disruption.

## Roll back code, not data

1. Pause Live using the independent kill or explicit manual pause. Verify an
   existing refresh session stops estimates. Keep private sharing unchanged.
2. Use a clean release checkout of the latest remote main. Review a scoped code
   revert or restore only affected source/tests/docs from a known-good release.
   The preceding UI release `d50d1442b2a1b72d6ca5e2bec6a5b48611f320d4`
   passed deployment checks (CI run 40453464995); it is a candidate baseline,
   not a blanket certification of feeds or future infrastructure.
3. Preserve newer datasets, dated context, activation policy, worker state and
   the user's index. Never reset the dirty working repo, force-push or revert an
   entire data-publication range. Test frozen-model/UI regressions and use a
   normal non-force push. If publication races a background data push, fetch and
   rebase the scoped code only; do not overwrite newer data.
4. Restart once with fresh operator approval if runtime coherence requires it.
   Verify Intelligence first, then only the intended private Live window. Never
   hot-reload the validator graph or disable the coherence gate.

## Outstanding evidence

First real nightly publication with the new Live-preparation stage still needs
its normal scheduled run. Roster-source timeouts may degrade preparation.
Full-game/two-viewer progression and game-state transitions need actual games.
No remote alert service, permanent telemetry store, always-on updater host,
public access or all-game capacity expansion is included in this release.
