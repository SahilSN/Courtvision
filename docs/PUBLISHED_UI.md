# Published interface

The private deployment shares one shell across Intelligence, Live and Historical
Replay. Workspace selection does not enable feeds or override rollout/runtime
gates. Unavailable Live selections recover to Intelligence with an explanation;
Historical Replay remains available independently of Live activation.

Within Intelligence, **Explore** offers Team ratings, Player ratings and Player
careers. Historical Replay has its own workspace. These are presentation labels; existing widget
keys/internal values are retained so player-preserving career/season links keep
working. The redundant published Mode selector is removed. The separate full
local dashboard retains its original mode discovery and historical/live paths.

The season picker starts with the current regular season. It applies to team
and player ratings; it remains visible but disabled for covered-season careers.
The independent replay catalog owns its own season/team/date selectors. Each page owns its relevant
player/season or game controls. Selecting a historical ratings season remains
explicit. No new archive coverage or game acquisition is included.

Update health sits below the navigation instead of above it. Times are labeled
Pacific time and formatted without raw timestamp precision. The panel remains
read-only; no worker, publication, policy or identity actions were added.

Shared page headers, metric cards, table borders, tabs and responsive spacing
are presentation only. Native controls retain labels, keyboard focus and touch
targets. Table data, ratings, coverage warnings, early-season eligibility,
replay spoilers, frozen models and all activation/validation guards are unchanged.
Raw error payloads were removed from the inline refresh-details drawer; owner
diagnostics remain available through the existing health/log workflow.

See [Historical Replay catalog](HISTORICAL_REPLAY_CATALOG.md) for the independent
completed-game index and explicit preparation states. Broader replay acquisition,
storage and processing remain separate from navigation or intelligence backfill.
