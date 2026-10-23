# Private beta operations

## Boundaries

Community Cloud runs `cloud/app.py` from GitHub main, in the published profile.
The Mac owns the once-nightly current-season update and finite historical
backfill. Cloud requests must not launch either worker, fetch NBA feeds, or
unpickle replay files. Frozen V7 and rating formulas are unchanged.

Private sharing is the access control. `COURTVISION_CLOUD_READY` is only a setup
latch, not authentication. Never weaken sharing or authentication to diagnose a
deployment. Never paste secrets into logs, reports, or commits.

## Read-only health checks

1. Confirm the latest **Deployment checks** run corresponds to the released SHA;
   both Ubuntu and macOS jobs should pass. A cancelled superseded run is not the
   current release's result. Replay JSON changes also trigger this workflow.
2. Open the authenticated beta and check Teams, Players, Career, Replay Pilot,
   and switching away from a replay. Check current-season freshness separately
   from historical archive completeness. Do not interpret a partial career as
   zero impact in missing games.
3. A new cookie-free request should redirect to Streamlit authentication, not
   display the app directly. This is a spot check, not proof against every
   authentication/access-control failure.
4. On the Mac, inspect the following without starting another worker:

```bash
launchctl print gui/$(id -u)/com.courtvision.historical-backfill
launchctl print gui/$(id -u)/com.courtvision.nightly-intelligence
```

Historical health is in `results/player_intelligence/.runtime/status.json`;
publication health is in the adjacent `publication.json`; rotating worker logs
are `backfill.log`. Nightly health/logs are in `results/.runtime/nightly/`.
These files are ignored local runtime state and must not be uploaded wholesale.

Source timeouts and upload failures are separate. Source retries retain saved
progress. Upload failures retain the last published archive and retry later.
Progress below a publication milestone is expected, not a deployment failure.

## Recovery

- Failed cloud render: inspect Manage app logs and the exact release SHA. Check
  artifact presence, pinned dependencies, and offline deployment checks first.
  UI renderer-only changes use an isolated namespace on rerun. This is not a
  general promise that every imported dependency hot-reloads.
- A host reboot interrupts current users. Obtain explicit approval before using
  **Reboot app**. After an approved reboot, verify app render, private access,
  player/career navigation and replay selection—not just a running-process log.
- Historical worker: LaunchAgent resumes at login and after unsuccessful exits,
  throttled by five minutes. Successful finite-task completion stops it. Sleeping,
  powered-off or logged-out Macs cannot process games. Inspect health before
  intervening. Do not start a competing manual backfill.
- Nightly updater: retains its once-at-1-a.m. schedule. A non-running nightly
  process between scheduled checks is normal. Diagnose missing/failed status
  before deciding whether to rerun a publishing job.

## Safe code rollback

Rollback is a new forward commit, not a force push or a reset of main.

1. Record the failing deployed SHA, latest passing check, and log excerpt without
   secrets. Identify the last working release; do not guess from a date alone.
2. Use a clean temporary clone of **latest remote main**, not the active Mac
   worker checkout. Its local branch can diverge from isolated publications and
   its dirty CSVs belong to the backfill.
3. Inspect every file changed by the candidate release. Revert only a code-only
   commit, or prepare a narrowly scoped recovery commit. Never blindly revert
   dataset publications, model artifacts, replay JSON, or secrets/configuration.
   Preserve newer team/player checkpoints. No reduction of published coverage.
4. Run unit regressions, compilation, `git diff --check`, and both entry-point
   smoke tests from that clean clone. Inspect the final diff, then push the
   forward recovery commit normally. A concurrent update requires a fresh safe
   retry; never force-push over it.
5. Verify CI for the new SHA and the authenticated app. No rollback or reboot was
   performed as part of the performance/health baseline.

## Local performance baseline

Reproduce with Python3.12 and the deployment dependencies:

```bash
PYTHONPATH=src python src/benchmark_published_app.py --repeats 3
```

Writes ignored `results/.runtime/performance/published-ui.json`. This bounded
single-session AppTest checks rendering and blocks feed requests/background
processes. It does not simulate concurrent users or use hosted memory metrics.
See [PERFORMANCE_BASELINE.md](PERFORMANCE_BASELINE.md) for measured results and
limits. Compare equivalent datasets and runtime versions before attributing a
difference to a code change. No automatic performance thresholds are set from
one local sample.
