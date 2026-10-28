# NBA CDN integration prerequisite — October27,2026

Requested: official NBA CDN fallback for the owner-only private beta, preserving
the frozen model, dated pregame context, exact identities and whole-pair checks.

Result: **blocked by HTTP403; provider integration is not complete or active.**

Both official POR@LAL0022600131 endpoints returned HTTP403 from the Mac:
`https://cdn.nba.com/static/json/liveData/boxscore/boxscore_0022600131.json`
and `https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_0022600131.json`.
The actual Community Cloud once-only check at2026-10-28T05:26:13.738043UTC
(October27 10:26p.m.Pacific) also returned HTTP403 on the first, boxscore request.
It stopped there rather than repeatedly querying a forbidden service. The host
play-by-play endpoint was therefore not tested independently.

Added a reusable, explicit access gate in `probe_nba_cdn.py`, with at most two
five-second requests, exact canonical NBA game/team identity checks, no ESPN ID
casting, no redirects/auth bypass, sanitized exception/status output. Nine focused
access/host-diagnostic tests passed; compilation and diff checks passed. These
checks prove access failure, NOT compatible data, model parity or reliability.

The temporary fifteen-minute operator request was removed after observation.
No restart, provider switch, activation/expiry extension, model or replay changes.
ESPN remains the existing provider. No CDN timeline adapter or automatic failover
was enabled: doing so would add requests/latency without a usable alternate feed.

Before further integration, establish permitted CDN access from an approved
deployment environment or evaluate a licensed provider. Once access works,
capture actual paired responses and test canonical/date/player validation,
score/box reconciliation, frozen-feature parity, source-labelled cache isolation,
stale expiry and recovery before enabling any fallback. Public endpoint access
does not itself establish redistribution permission or availability guarantees.
