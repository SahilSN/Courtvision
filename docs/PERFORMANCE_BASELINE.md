# Local published-app baseline — 2026-10-23

Measured at 23:19 UTC on macOS 27.0.1 ARM64, Python 3.12.2, existing deployment test
environment. This is **local AppTest execution**, not hosted cold start, browser
paint time, network latency, cloud memory usage or a load test. OS/font caches
were not purged. The app code matches the deployed 5394575 release; the local
historical backfill may contain more unpublished games than the cloud archive.

Fresh benchmark process: first app render 3.875 s; benchmark startup through that
render 4.899 s. Imports before AppTest execution are included only in the latter.

| View | First selection (s) | Median of 3 warm reruns (s) |
| --- | ---: | ---: |
| Teams | 0.094 | 0.093 |
| Players | 0.089 | 0.081 |
| Player Career | 0.283 | 0.098 |
| Replay Pilot | 0.074 | 0.067 |

First selection is not a separate cold process for each view. All selections use
the same AppTest session, current 2026–27 season, default player, and first replay;
these samples are not worst-case coverage of every historical season/player.

Peak local process high-water memory 449.9 MiB for the entire benchmark (imports
included), not incremental per-view memory. Observed app feed requests0;
background subprocesses0. These results do not establish a cloud memory limit
or safe concurrency level.

Deployment health: GitHub run 40038567113 passed both Ubuntu and macOS checks for
5394575. The Mac historical LaunchAgent was running; last nightly status was
successful. These are point-in-time checks, not continuous availability proof.

Next measurements before a wider rollout: fresh hosted process readiness during
an explicitly approved restart window, real browser first-paint/interaction
timings, representative long-career/historical cases, hosted memory telemetry,
and bounded concurrent-user tests. Do not restart production or disable private
access to obtain a baseline. Tester feedback remains deferred.
