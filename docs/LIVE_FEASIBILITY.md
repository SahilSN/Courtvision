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

Before enabling hosted Live:

1. Run the same bounded diagnostic on the actual Community Cloud runtime through
   an explicitly scoped operator-only mechanism; do not expose an unrestricted
   probe or enable Live merely to test outbound access.
2. Verify provider schema and event ordering on active, final, delayed and
   corrected games; compare scores/clock and team mapping with existing validators.
3. Measure end-to-end inference, memory and refresh load on that host, not just
   HTTP latency. Prove session refreshes share cached data and do not multiply
   upstream polling per viewer.
4. Set timeout/backoff/stale-data behavior and an operator disable path; establish
   provider terms/usage suitability before a wider service.
5. Only then propose a small hosted Live release for approval. Keep frozen V7,
   historical replay, private sharing and the Mac nightly schedule unchanged.
