# Owner-beta Live readiness and recovery

## October 27 fixes

Exact official NBA profile mappings added for Jaden Akins (NYK1643022), Ebuka
Okorie (DET1643536), Darius Acuff Jr. (SAC1643411), Alex Karaban (SAC1642284),
Emanuel Sharp (SAC1643567) and Tarris Reed Jr. (SAS1643542). Includes bench/DNP
names before participation; no ESPN IDs are cast to NBA IDs and no fuzzy matches.
Profile URLs are retained with each season/team-scoped mapping and regression.
Mikel Brown Jr. was fixed separately. Current-roster observations are not a
guarantee against future signings, trades, source errors or unmapped names.

## Autonomous preparation, not autonomous release

`run_live_preflight.py` is a bounded Mac LaunchAgent every 15 minutes, separate
from nightly records, backfill and replay expansion. It is inactive unless the
existing finite owner-beta policy and dated manifest are valid. It starts one
hour before the first selected tipoff, validates at most four existing matchups,
and retries official NBA roster acquisition plus ESPN roster inspection using
the existing 65-second between-call budget and bounded HTTP requests.

The original day context is read-only: no post-tip record recomputation. Manifest
issuance, expiry, allowed games and context digest cannot change. Publication
uses a clean latest-main clone, stages only roster/review/readiness artifacts,
and non-force pushes. Timestamp-only changes do not trigger another deployment.
Concurrent changed context, changed rollout, newer official evidence or verified
roster regression cause a safe retry, never overwrite. Workers save their own
status/pending names under `results/.runtime/live-preflight/`; user index untouched.

Successful exact official roster identities resolve automatically through the
existing dated artifact reader, without another code patch or host restart.
Timeouts retain still-valid same-day evidence using its ORIGINAL per-team
timestamp, never resetting the 36-hour maximum age. Missing, stale, ambiguous or
conflicting identity data stays unavailable and enters the review queue.
Empty pregame summary rosters are explicitly not inspected, rather than silently
counting as a successful review. Reviewed exact mappings remain a fallback.

**Known source limitation:** direct official NBA roster requests timed out and
the alternative official directory/CDN returned HTTP403 on this Mac. No TLS,
authentication or validation bypass is installed. If official sources remain
unavailable for a genuinely new identity, human review of an official profile
is still required. This implementation does not promise all future games will
always be available, purchase a provider, or extend the private beta policy.

## Viewer recovery and useful errors

Absent/expired cache now preserves only a sanitized error CLASS for display:
identity review needed, score/box sections disagree, provider timeout/HTTP error,
or generic verified-context wait. Raw provider errors are never rendered.
The last good whole-pair snapshot, original verification time, 60-second expiry,
single-flight ownership, 15-second backoff and existing two score-only attempts
are unchanged. No inconsistent pair replaces a good pair and no estimates are
invented. Opt into the existing 15-second refresh switch to recover automatically
when a coherent source arrives; manual refresh remains the default.

Data readiness lists pending names for the selected teams and distinguishes a
failed roster refresh from an actually unresolved identity. Inspect local
`status.json`, `launchd.log`, `launchd-error.log` in the preflight runtime folder;
hosted readiness is the last published snapshot, not proof the Mac is awake.
