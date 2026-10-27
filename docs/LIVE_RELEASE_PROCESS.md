# Private Live release process

## Mandatory checks

1. Publish only reviewed code/config from a clean latest-main checkout; preserve
   automated datasets and never force-push the diverged local checkout.
2. Before offering Live, compare loaded validator functions, cache methods,
   reviewed identity/box policy literals and cross-module imported bindings with
   deployed source. Repeat at every refresh through the rollout guard. Missing,
   stale or partially deployed code fails closed; Season Intelligence stays usable.
   This is runtime-coherence checking, not cryptographic signing or feed approval.
3. If blocked, inspect sanitized owner diagnostics. Do not reload a module graph
   while viewers are running. Obtain approval for a restart that interrupts
   viewers, then repeat the runtime/current-feed checks.
4. Use only exact, dated NBA/ESPN/team/player mappings and prior-only records.
   Verify coherent advancing snapshots and matching timeline/header/box scores.
   Verify stale retention, expiry/unavailable behavior and subsequent recovery.
5. Require private host access, independent host opt-in, dated expiring allowlist
   and kill override. Default to Season Intelligence and manual refresh.
6. Check actual hosted scoreboards, frozen predictions, both box tables and
   opt-in refresh. Remove temporary activation and verify existing-session pause
   and default-navigation recovery. Remove diagnostic requests as well.

## Fast coverage expansion

Current reviewed limit is four simultaneous games. Broader game coverage
does not require changing the frozen model or removing reconciliation checks.
For the next release, validate four distinct current games and exact participating
identities, then measure a bounded four-caller hosted workload before raising the
allowlist, view and cache capacities together. Keep request limits, short expiry,
rollback and private access. If a candidate fails, exclude it rather than treating
unavailable identities or scores as zeros. Do not expand to unrestricted discovery
or automatically create new scheduled monitoring jobs.

Passing an archived CPU workload is not proof of actual current-feed correctness;
passing several current snapshots is not a production-load certificate. Record
which evidence passed and which checks remain before increasing the limit.

## Earlier verification on October26

180 tests passed on Python3.10 and3.12; deployment smoke and syntax/diff checks
passed. Owner-only Community Cloud request runtime-gate-settled-20261027 reported
runtimeReady=true, currentIdentityCode=true, currentMinutesCode=true and a passing
489-state current-game pipeline. An earlier report omitted runtimeReady during
source deployment and was not accepted as evidence. Temporary requests removed.

Read-only four-game assessment: MIN@CLE passed; CHI@BOS, DAL@MIA and IND@MIL each
failed involved-player identity validation. These games are not yet approved for
expanded coverage. Verify exact official player identities before retrying; do
not interpret unavailable games as a completed four-game rollout.

## Repeatable readiness diagnostic

`PYTHONPATH=src .venv/bin/python src/check_live_deployment.py --game-ids <1–4 exact NBA game IDs>`
checks the complete dated selection and loaded runtime before network/model
work, then runs two concurrent per-game rounds separated by 16 seconds (16–30
configurable). The existing HTTP limits, strict joined validation, frozen CPU
artifacts and shared raw cache remain in force. This is an explicit bounded
operator command, not a new scheduler, automatic discovery or an activation.

The JSON identifies validated/stale/failed observations and forward movement in
elapsed game time or event number. Completed-only, unchanged, corrected-only,
stale, missing and failed observations do not certify progression. Exit zero
means the selected current-feed check passed, NOT production release approval;
canEnableLive is always false. The fixed owner-only diagnostic kind `progress`
uses the same check with explicit gameIds, two rounds/30-second separation,
existing 15-minute request expiry and once-per-container claim. It returns only
public IDs/scores/timings/states/error classes; no raw payloads or identities.

October26 late-game identity additions are exact season/team-scoped official NBA
profile mappings in reviewed_live_players.py. Brandon Williams is disambiguated
from a retired namesake only by that explicit reviewed scope; conflicting
reviewed matches and other scopes remain ambiguous. This is not fuzzy matching.
