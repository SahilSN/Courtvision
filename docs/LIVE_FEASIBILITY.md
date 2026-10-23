# Hosted Live feasibility — not activated

Live remains disabled in the published beta. No refresh schedule or data
publication is introduced by these diagnostics.

`src/probe_live_access.py` makes at most two read-only ESPN requests: one dated
scoreboard, then one summary for a numeric event ID returned by that scoreboard.
Each request has a five-second socket timeout, a 2 MB response cap, no redirects,
no application retries, and verified TLS. It uses the installed trusted certifi
bundle when available; otherwise the platform trust store. It prints only
access/schema measurements and error types, not feed bodies or credentials.

```bash
python src/probe_live_access.py --environment mac-local --date 2026-10-23
```

Mac check at 23:37 UTC: scoreboard HTTP200, 12 events, 199072 bytes, 0.172 s;
one summary HTTP200, 541 plays, box score present, 480300 bytes, 0.217 s.
This proves only point-in-time local access—not cloud access or provider
correctness. An initial local platform-CA failure was resolved by selecting the
already installed trusted CA bundle; certificate validation was never disabled.

The manual **Live access probe (manual, read-only)** GitHub workflow has read-only
repository permissions, no schedule, no dependency installation and no publishing
step. Its results describe a GitHub Ubuntu runner, not Community Cloud. Failed
access returns a failing exit code; an empty schedule reports scoreboard-only
verification, not a successful end-to-end live check.

## Actual Community Cloud access check

Verified at 23:49:54 UTC on October23,2026 through a reviewed deployment request
(`community-live-access-20261023-a`), with owner-log-only results:

- Scoreboard: HTTP200, 12 events, 199104 bytes, 0.457 s.
- One event summary: HTTP200, 541 plays, box score present, 480300 bytes, 0.218 s.
- Report: `access_verified`, environment `community-cloud`.

The request expired after 15 minutes at most and was removed immediately after
verification. Exclusive claim-file creation prevents duplicate attempts across
concurrent viewers and reruns in the same container; failure does not retry.
A replacement container could attempt once again inside the short window.
No viewer controls, recurring schedule, public diagnostic output, or Live-mode
activation were added. Optional diagnostic errors cannot block the dashboard.
An initial hot-deployment import error was fixed and the dashboard recovered
without reboot; subsequent entry-point smoke tests pass.

This closes the outbound-access gate only. It does not measure host inference,
prove correct event attribution, or establish concurrency/memory capacity.

## Remaining gates before enabling hosted Live

1. Validate the full existing provider path on the host, including any secondary
   NBA/roster requests. The successful two-endpoint probe does not prove those
   dependencies are reachable.
2. Verify provider schema and event ordering on active, final, delayed and
   corrected games; compare scores/clock and team mapping with existing validators.
3. Measure end-to-end inference, memory and refresh load on that host, not just
   HTTP latency. Prove session refreshes share cached data and do not multiply
   upstream polling per viewer.
4. Set timeout/backoff/stale-data behavior and an operator disable path; establish
   provider terms/usage suitability before a wider service.
5. Only then propose a small hosted Live release for approval. Keep frozen V7,
   historical replay, private sharing and the Mac nightly schedule unchanged.

Shared polling design to validate next: one cached provider snapshot per game
and process, a bounded TTL, in-flight request coalescing, explicit stale-data age,
and bounded retention. Viewer reruns must not each fetch the same feed. Cache
keys must include provider/game/context; historical immutable replay caches must
remain separate. This is a design gate, not an implemented hosted polling loop.
