# Games continuing past Eastern midnight

Live keeps the original scheduled game date and its original dated pregame
context. It does not label an October26 game as October27 or rebuild its records
using results acquired after tipoff.

The shared date policy permits today's date, plus yesterday strictly before
06:00 America/New_York. At06:00 yesterday is refused, including cached estimates.
The window uses local calendar dates/hours, including daylight-saving changes.
Older/future/malformed dates and naive clocks fail closed.

During the overnight window a previous-day game must have source state `in` or
`post`; a postponed/unstarted `pre` game cannot generate an estimate. `post`
permits the existing game's final transition, not progression certification.
All exact event/date/team/player, whole-pair score, pregame cutoff and frozen V7
checks remain. The rollover policy does not relax reconciliation or retention.

The reviewed rollout file still needs both operator gates, an exact game
allowlist, valid issuance/expiry and its original game date. Midnight does not
extend its expiry. Kill/expiry continues to pause requests on refresh.
Missing or replaced original dated context remains unavailable; no fallback to
the next day's context is permitted. Nightly jobs and their datasets are unchanged.

The readiness diagnostic queries the explicit context's original schedule date
and uses production date eligibility by default. Its existing explicit `today`
and analysis `as_of_date` overrides remain deterministic/offline test hooks only;
normal hosted probes do not set them. Runtime coherence includes the shared
policy and its cutoff, so stale imports block rather than silently mixing rules.

No Live activation, sharing change, host reboot or permanent monitoring is
part of this fix. A bounded late-game backend check is not a full-game or
two-viewer hosted certificate.
