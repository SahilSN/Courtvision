# Inactive dated-context / frozen-model join

`cloud_live_analysis.analyze_live_snapshot` now joins the strict offline daily
context reader, jointly validated cached timeline/box, unchanged feature builder
and frozen V7 prediction function. No dashboard, live provider or worker imports
this entry point. Hosted Live remains disabled.

Current Eastern game date and exact published prior-day coverage must pass
before loader or inference. The published ESPN event mapping is enforced inside
the snapshot validator. Missing/corrupt/stale context does not become neutral.
Production callers omit as_of_date; that override exists only for deterministic
archived tests. Caller owns immutable model/scaler/device artifacts and bounded
HTTP loader, cache and optional progress tracker. No new model training, weights,
feature definitions, smoothing or inference math is introduced.

Returned predictions must align with the timeline and have finite probabilities
in [0,1]. A retained snapshot can still be analyzed but is explicitly marked
stale_snapshot. Other presentation-state tokens are possibly_stalled,
progress_unknown (no tracker), or validated_snapshot (not a claim of current
upstream movement). No UI component or refresh timer is added. Missing context
is an exception, not a half-filled successful result. Warm cache hits still
require the context file to validate on each call.

Offline tests use actual frozen CPU artifacts and archived two-overtime feed/
box fixtures plus synthetic verified opening-night context. They cover a full
join, date/coverage/corrupt-file rejection before fetching, wrong ESPN mapping,
and retained stale predictions. This is NOT a current game or Community Cloud
end-to-end certification. Inference and context/file parsing are not shared or
memoized per snapshot; concurrency costs still require measurement.

Next gates: actual UI contract and explicit unavailable/stale messages, broader
regulation/legitimate-correction/current-identity coverage, whole-pipeline host
CPU/memory/concurrency checks, then an explicitly approved limited Live rollout.
