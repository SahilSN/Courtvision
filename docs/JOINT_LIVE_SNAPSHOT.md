# Inactive joint timeline/box cache integration

`cloud_live_bundle.get_live_bundle(cache, canonical, loader)` is a separate
prototype, not imported by the app or live/historical providers. Hosted Live
remains disabled. Caller supplies the shared bounded LiveSnapshotCache, verified
canonical context and its own bounded I/O loader returning public event/summary
JSON. An explicit canonical espnEventId, if supplied, must match the snapshot.

The loader deep-copies and validates both timeline and traditional box **before**
returning raw JSON to the cache. A malformed, lagging or unreconciled panel thus
cannot evict the previous jointly valid pair. The cache stores JSON only and
coalesces concurrent fetches. Each caller independently reconstructs DataFrames
from its snapshot copy, so panel mutations cannot affect other callers.

Returned age_seconds/is_stale/refresh_error_type describe the same snapshot for
both panels. Refresh errors retain the previous pair only within the configured
maximum age; cold invalid data or expired retained data is unavailable. No
partial panel mixing, neutral data or invented stats are returned. Different
game/season/date/schema contexts use separate keys. Canonical team identity is
rechecked even on a warm cache hit.

Current implementation intentionally repeats pure normalization for validation
and per-caller reconstruction, including the box adapter's timeline check. It
does NOT coalesce CPU inference/normalization, and this cost must be factored and
measured before hosted integration. Existing loader timeouts, waiter timeout,
container-local cache and encoded-byte/actual-memory limits still apply.

Acquisition freshness is NOT upstream event progress: an upstream server may
repeat an old but internally consistent response. Progress-age detection and
the corresponding UI wording remain required. This code adds no timer, HTTP
loader, model inference or frontend state. It does not yet join dated pregame
context or certify the full hosted pipeline.

Tests use the archived two-overtime game with HTTP blocked: concurrent callers
share one fetch; independent tables; box lag rejected with bounded stale pair;
recovery clears errors; partial cold feed and over-age failure are unavailable;
wrong canonical teams cannot reuse a warm cache; duplicate corrected events
retain the previous pair. Broader regulation/current-live/legitimate correction
fixtures, CPU/resource measurements and UI adaptation are still pending.
