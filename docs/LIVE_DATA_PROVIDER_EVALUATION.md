# Production live-data shortlist — evaluated October 26, 2026

This is a documentation-based shortlist, NOT a measured performance comparison,
purchase, legal clearance or completed integration. Existing ESPN validation and
frozen model remain unchanged. No account, subscription or API key was created.

## First evaluation candidate: Sportradar NBA

Official NBA Push Events documents real-time game events with trial/production
access levels: https://developer.sportradar.com/basketball/v5/reference/push-events
Its simulations documentation includes NBA recordings and REST/push replay,
allowing repeatable tests outside game windows:
https://developer.sportradar.com/getting-started/docs/simulations

Reason to evaluate first: repeatable recorded-game tests plus documented event
streaming. This is an inference about testability, not a claim that the live
feed has lower latency or atomic box/play/header updates. Confirm the current
NBA API version, coverage, quotas and commercial rights before implementation.

## Second candidate: SportsDataIO NBA

NBA API documentation includes current/final play-by-play endpoints:
https://sportsdata.io/developers/api-documentation/nba
Its timing guidance recommends3–5s score/box polling for real-time subscriptions
and states a minimum3s content cache:
https://sportsdata.io/help/refresh-rates-feeds-and-timing
Commercial product/display/storage rights must be confirmed for Courtvision:
https://sportsdata.io/help/data-rights-and-licensing-questions

Reason to compare: documented REST refresh guidance fits a polling backend.
It does not prove that independently fetched sections always reconcile or that
a personal/testing package permits the intended published product.

## Required trial and selection gates

Ask both providers for the exact NBA play-by-play + player/team box package,
stable identity crosswalks, corrections/revision semantics, reconnect/replay
support, historical availability, quotas, contract/SLA and total quote. Confirm
display, caching, derived ratings/probabilities, retention and redistribution
rights for this app with the vendor; do not infer rights from technical access.

Run both in SHADOW mode alongside ESPN for at least one full game. Measure
timestamped event freshness, cross-section reconciliation, observed delay spans,
missing identities, correction recovery, request volume and CPU/memory. Replay
the same recordings with network interruptions. Do not mix one provider's score
with another's box/play data to manufacture agreement. A new adapter must pass
the same exact identity/date/regular-season/whole-pair contracts and frozen-model
feature tests before any switch.

Choose after measured results and a suitable trial/contract/budget are available.
No reliable current price or independent live latency/SLA measurement was obtained
in this evaluation, so no cost/performance winner is asserted.
