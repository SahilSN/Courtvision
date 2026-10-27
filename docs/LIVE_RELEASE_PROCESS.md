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

Current reviewed limit remains two simultaneous games. Broader game coverage
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
