# Prepared, default-disabled hosted route

Live is still OFF. This preparation creates no rollout JSON, changes no host
environment setting, and does not change private sharing or legacy live/replay.

Two independent deployment gates must both pass before navigation is offered:

1. COURTVISION_ENABLE_LIVE_BETA=1 in the host environment.
2. A reviewed cloud/live_rollout.json containing schemaVersion1, enabled=true,
   current season/Regular Season, Eastern gameDate=today, explicit timezone-aware
   issuedAt/expiresAt (maximum24h lifetime), and1–4 unique canonical regular-season
   gameIds. The exact IDs must match published dated context when selected.

Missing/corrupt settings, wrong dates, expired windows and oversized/duplicate
allowlists fail closed.
COURTVISION_DISABLE_LIVE_BETA=1 overrides both gates immediately on the next
rerun. These gates are rollout controls, NOT authentication. Community Cloud
private-sharing authentication must remain enabled; setup readiness is not auth.

When allowed, Workspace defaults to Season Intelligence. Live Beta selection
loads only the guarded four-game-capacity view. On kill/expiry, a retained Live selection
is reset to Season Intelligence; legacy full discovery stays disabled. A view
exception shows a sanitized unavailable warning and return path, not traceback
or a guessed estimate. No activation file is shipped with this change.

Each refresh fragment rechecks the operator gate before any HTTP or model work;
kill/expiry shows paused and makes no new feed request. On a full rerun, navigation
also resets to Season Intelligence. In-flight calls are not remotely cancelled.

Rollback: set the kill switch or remove the rollout JSON. Confirm an existing
Live session returns to Season Intelligence on rerun and that both panels have
stopped making requests. No service reboot or data rollback is required for the
logical gate; host environment changes may follow the platform's apply/restart
behavior. Keep rollout expiry short.

Tests exercise gate validation, environment opt-in, kill override, normal
navigation default, isolated mocked Live routing, stale selection recovery,
and zero HTTP from the published default route. Real Live activation remains
conditional on the scheduled advancing-feed check; do not set either gate early.

Operator logs use COURTVISION_LIVE_STATE with public game ID, presentation state,
refresh duration, snapshot age and exception class only. Repeated same-state
events are throttled to once per60s/game (state changes emit immediately),16-game
process-local capacity. No raw error messages, payloads or user/session IDs are
logged. Durations include network/cache/UI work, not just model inference.
