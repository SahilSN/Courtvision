# Network-free provider adapter prototype

`src/cloud_espn_adapter.py` is **inactive**: neither the dashboard nor the existing
live/historical providers import it. It does not fetch feeds, change model
weights/features, publish data, or enable hosted Live.

## Implemented and validated

- Accept a verified canonical NBA regular-season game context plus ESPN event
  and summary JSON. ESPN IDs are never cast into NBA game/player IDs.
- Validate matching event IDs, season/year/type, Eastern schedule date, exact
  home/away team identity and agreement between event and summary.
- Resolve involved athletes using unique exact normalized full names in the
  bundled NBA registry. Unknown/ambiguous participants block the prototype;
  no network roster lookup or silent zero-impact identity is used. This is not
  a complete identity service for every current player or name variant.
- Reuse unchanged `normalize_espn_play` and `preprocess_live_game`. The captured
  archive has corrected plays with nonchronological sequence numbers: preserve
  the published play array, reject duplicate identities/sequences, and validate
  resulting clock order. Do not sort by sequence number or merge old snapshots.
- Reject missing scores, invalid clocks, mismatched team inference and a last
  play score that has not reconciled with the summary header. Temporary feed lag
  therefore remains unavailable/stale, not a fabricated current state.
- Compute pregame W–L only from strictly earlier calendar dates, matching prior
  game IDs and dates against an independent verified schedule. Require matching
  regular-season provenance and a catalog completeness watermark through the
  previous day. Reuse existing current-season smoothing without changing raw W–L.

The completeness watermark is an **upstream verification assertion**, not a
fact inferred from the latest row or from the same incomplete history. A live
deployment still needs a verified schedule/publication mechanism to produce it.
The opening-night zero-game case is valid only with that coverage assertion;
missing expected games must never become a neutral record.

## Evidence and limits

`src/fixtures/espn_contract_0022500001.json` is a compact captured archived feed
for HOU@OKC, October21,2025, ESPN event401809243 / NBA game0022500001. It records
source/capture time and retains all595 play records, identity metadata and score
headers while omitting external images, links and unrelated box-score details.
It is not a current live fixture or a claim that the archive never changes.

Tests normalize594 usable states (initial unusable possession state filtered by
the existing preprocessor), verify the final125–124 score and sixth period,
test a first-quarter prefix without a final-outcome feature, and run the output
through unchanged frozen V7/scaler CPU inference. A parity test compares all
shared timeline columns with the existing ESPN normalizer on the identical
captured feed, using the same offline identity mapping and blocked HTTP.

Additional tests reject wrong games/seasons/types/dates/teams, unknown players,
duplicate/scrambled/empty plays, missing scores, invalid clocks, unreconciled
headers, missing prior games, stale completeness, duplicate history and bad
record dates. These do not prove every correction, alias, overtime or late-feed
case in production. Current baseline:115 local unit tests pass on Python3.10
and3.12, with existing deployment checks retained.

## Next gates

1. Produce a versioned, independently verified canonical schedule and complete
   prior-game context for the hosted current season; test publication gaps.
2. Build a reviewed identity alias/ID artifact for unresolved participants, not
   fuzzy matching or a neutral player fallback.
3. Capture additional regulation/delayed/corrected fixtures and test the adapter
   with the inactive shared raw-JSON cache. Validate native ESPN box-score display
   separately; existing advanced/traditional NBA box-score paths are unchanged.
4. Measure whole-pipeline CPU/memory on the actual host and define stale/error
   messaging before proposing a small explicitly approved Live release.
