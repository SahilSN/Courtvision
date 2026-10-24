# Hosted Live provider and cache audit — 2026-10-23

## Findings: ESPN access alone is not the complete path

The actual Community Cloud scoreboard/summary probe succeeded. Inspection of
the existing full provider shows additional dependencies:

| Stage | Current implementation | Hosted readiness gap |
| --- | --- | --- |
| Canonical game mapping | `espn_live.resolve_espn_event` calls `resolve_nba_game_metadata`, which calls NBA ScoreboardV3 through `game_catalog` | NBA metadata is required before the ESPN event is selected; the ESPN probe bypassed it |
| Player identity | `current_roster_name_map` calls CommonTeamRoster with a 30-second timeout; static NBA names are fallback | Roster failures are swallowed and may leave players unresolved; recent/ambiguous names need explicit validation |
| Pregame context | `build_pregame_context` first checks the local season training table for regular-season games; otherwise `fetch_team_record_before_game` uses TeamGameLogs with a 60-second default timeout | Local training tables are not guaranteed on the host for today's game; the network fallback is not established by the probe |
| Provider fallback | `fetch_true_live_play_by_play` tries ESPN and may fall back to NBA play-by-play | Failover must be bounded and visible, not conceal missing identity or multiply timeouts |
| Analysis and rendering | Preprocessing, frozen V7 inference, score validation and downstream player/box-score views | HTTP access is not proof of end-to-end correctness, latency or resource use |
| Live box-score panel | `dashboard.cached_live_box_score` calls `box_score.fetch_box_score`, using BoxScoreTraditionalV3 and BoxScoreAdvancedV3 | The ESPN summary probe does not validate the separate NBA box-score rendering path |

No current local provider calls, model formulas, replay semantics, or pregame
record smoothing were changed by this audit. Existing lru-cached metadata does
not itself coalesce simultaneous misses or define feed freshness/failure policy.

## Inactive shared-cache prototype

`src/live_snapshot_cache.py` is not imported by the dashboard or live provider.
It is tested infrastructure, not a hosted Live feature or shared polling loop.

- One public JSON snapshot per explicit provider/game/season/season-type/date/
  schema key. No private/session-specific data belongs in this cache.
- Default 15-second TTL, maximum usable age 60 seconds, 15-second error cooldown.
- Simultaneous viewers coalesce onto one in-flight loader per key. Other games
  do not hold the global lock during HTTP work. Waiters have a five-second wait
  budget; an existing sufficiently recent snapshot may be returned as explicitly
  stale. Missing/too-old data fails closed with a generic unavailable error.
- Default 16 entries, 2 MB encoded JSON per snapshot, LRU eviction of idle entries.
  In-flight capacity is bounded; no active refresh is evicted to admit more work.
  These are encoded-payload limits, not a measurement of Python process memory.
- Deep copies prevent one viewer from mutating another viewer's cached feed.
- Unsupported/non-finite/oversized JSON is rejected without overwriting good
  data. Raw provider error details are not passed to viewers.
- Loader HTTP timeouts remain mandatory. A waiting viewer timing out does not
  cancel an already running loader. Each host process/container has its own
  cache; multiple replicas require a separate coordination design.

Tests cover concurrent misses, TTL refresh, stale/error age, cold-failure cooldown,
per-context isolation, eviction/admission, oversized/malformed payloads, copied
results and waiter timeout. No network is used by these tests.

## Next implementation gate

A separate inactive adapter now exercises the network-free approach; see
[CLOUD_ADAPTER_PROTOTYPE.md](CLOUD_ADAPTER_PROTOTYPE.md) for captured-feed parity,
coverage checks and the remaining schedule/identity publication requirements.

Before wiring this into a hosted path, validate a cloud-safe canonical game and
player identity mapping and pregame record source. Do not silently substitute
neutral values, mix preseason records, or treat unresolved identity as zero
impact. Then use captured feed fixtures to test corrections, ordering, delays,
halftime/overtime and final states through preprocessing and frozen inference.
Only after that should one process-owned cache instance be integrated into a
small explicitly approved hosted Live release. Do not create a cache per viewer
or cache an entire mutable session. Keep hosted Live disabled in the meantime.
