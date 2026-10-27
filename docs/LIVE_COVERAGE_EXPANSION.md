# Four-game private beta preparation — October26,2026

Prepared capacity: four explicit reviewed games, not unrestricted discovery.
Allowlist, view, shared raw cache, progress tracker and scoreboard cache use the
same reviewed maximum. Duplicate/oversized lists still fail; dated context,
private host access, runtime coherence, independent opt-in, kill and expiry
remain mandatory. No model, replay, historical minutes or nightly-job changes.

## Identity additions

Exact2026–27/team scope; official profile URLs retained in reviewed_live_players:

- CHI: Caleb Wilson1643410, Tobe Awaka1643591, Dailyn Swain1643517.
- CHI: Jaylin Sellers1643637, independently returned by official
  CommonTeamRoster(TeamID1610612741,Season2026–27), PLAYER_SLUG jaylin-sellers.
- DAL: Morez Johnson Jr.1643516, Sergio de Larrea1643547.
- MIL: Nate Ament1643417, Brayden Burries1643415.

Unknown/ambiguous participating identities still block. NBA IDs were not inferred
from ESPN IDs. Regression coverage checks exact names and wrong-team/season scope.

## Actual host capacity evidence

Owner-only request four-callers-20261027-0140 on Community Cloud/Python3.12.15:
pipeline_baseline_passed; four concurrent frozen594-state calls1.6243seconds total;
whole-process peak501.3MiB; model load0.0046seconds; sequential0.589/0.363/0.3273s.
This is an archived CPU/shared-cache workload, NOT four-game HTTP/browser load
certification. The diagnostic is explicit, once/container,15min expiry, no UI.

## Feed/release boundary

CHI@BOS and IND@MIL passed full joint context/feed/box/frozen prediction checks
after additions (472/311states,29players each). MIN@CLE passed494states on retry.
DAL@MIA still showed intermittent timeline/header score lag at the check; it
must pass coherent snapshots before approval. No validation relaxation.

Publishing this preparation does not activate Live. Runtime verification must
confirm the new identity policy and capacity are actually loaded. If stale code
is detected, request approval before a service-interrupting restart. Only after
runtime/current-feed verification may a short-lived four-game allowlist be used;
verify actual hosted selection/refresh/stale handling and rollback. Remove every
temporary diagnostic/rollout activation after the test.
