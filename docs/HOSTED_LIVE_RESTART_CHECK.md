# Hosted validator restart check — October26,2026

Root evidence: the running host reported currentIdentityCode=true but
currentMinutesCode=false, while the updated source existed on main. Both original
trial games failed timeline identity validation. A source pull was not proof that
all imported validators in the long-running Python process had been refreshed.

The user explicitly approved a brief service-disrupting app restart. The host
restarted at01:25:16UTC October27. A fresh once-only operator diagnostic reported
both currentIdentityCode=true and currentMinutesCode=true; both canonical trial
games passed current feed/box/frozen prediction checks (472 and483 states).
The prior identity failure did not recur in those checks. No identity guessing,
model/scaler change or validator weakening was needed.

A short-lived private two-game view was verified in the actual hosted browser:
MIN@CLE scoreboard112–111,Q4 0:26, model probabilities72.3%/27.7%, chart and two
traditional player tables including Meleek Thomas; WAS@CHA103–110,Q4 0:00,
89.0% home probability, chart and box. These remain frozen-model snapshot
probabilities, not a new terminal100% rule. Manual refresh and the opt-in15s
switch were exercised. Missing minutes remain unavailable, not inferred zeros.

The temporary diagnostic request and rollout allowlist were removed after the
checks. Host opt-in alone does not enable Live. Private access, nightly jobs,
historical validation and frozen V7 are unchanged. This limited verification is
not a claim of broad live-production readiness or load testing.

For future changes to imported feed/identity/box validators, verify runtime code
and current-feed behavior, not just deployment-pull logs. If a restart is needed,
explain viewer interruption and obtain approval before confirming it. Do not
force-reload module graphs concurrently or weaken validation to avoid a restart.
