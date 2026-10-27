# Published interface

The private deployment shares one shell across Intelligence and Live. The
workspace switch is shown only while a verified Live window is eligible; it
does not enable feeds or override rollout/runtime gates.

Within Intelligence, **Explore** offers Team ratings, Player ratings, Player
careers and Replay collection. These are presentation labels; existing widget
keys/internal values are retained so player-preserving career/season links keep
working. The redundant published Mode selector is removed. The separate full
local dashboard retains its original mode discovery and historical/live paths.

The season picker starts with the current regular season. It applies to team
and player ratings; it remains visible but disabled for covered-season careers
and the four-game replay collection. Each of those pages owns its relevant
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

Before expanding historical replay in production, retain the current curated
collection label and coverage limits. Broader catalogs, storage and processing
are separate deployment work—not unlocked by the new navigation.
