# Replay preparation priority comparison — October 27, 2026

Measured three actual five-game 2025–26 batches in each configuration while the
owner used the laptop normally. Same frozen model, validation, child batch size,
single-thread library settings and publication policy; no extra concurrency.

| Setting | Five-game durations | Median | Processing throughput |
| --- | --- | --- | --- |
| Previous low | 48.242s, 52.770s, 46.164s | 48.242s | 6.12 games/min |
| Normal | 9.008s, 8.689s, 9.293s | 9.008s | 33.35 games/min |

All 15 games per setting were prepared. Approximately 5.45x processing throughput
in this sample. Durations are worker checkpoint intervals including child startup,
inference, export/validation and bookkeeping, excluding pauses between batches.
This is an observational comparison, not a controlled benchmark or a guaranteed
archive completion estimate. Different game sizes, filesystem/model caches,
thermal conditions and concurrent user activity can affect results. Laptop UI
responsiveness, battery drain, thermals and system-wide CPU were not quantified.

The old worker's effective CPU nice value was 19 (LaunchAgent plus application
deprioritization), with Background process type and low-priority I/O. The new
worker was verified at nice 0, Standard process type and normal I/O. Thus this
tests the whole scheduling configuration, not CPU priority in isolation.
Restart time and the interrupted transition batch were excluded from the normal
sample. The timing observer now requires a matching priority checkpoint.

Normal mode remains enabled at the owner's request for a responsiveness trial.
The progress page displays actual low/normal CPU-priority category. Existing
validation, locks, timeout/disk safeguards, no daily cap and nightly-only
publication are unchanged. Request a return to low priority if normal laptop
use becomes noticeably less responsive or power/heat becomes undesirable.

Exact local evidence (not published telemetry):
`results/.runtime/replay-expansion/priority-comparison/low-20261027T221803.json`
and `normal-20261027T222127.json`.
