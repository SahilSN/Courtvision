# Replay-inspired Game Center preview

Only the gated archived `cloud/live_preview.py` changes. Community Cloud's
entry point and existing local live/replay screens remain untouched. No model,
feature, impact, identity or feed logic changes. This is a design iteration,
not a newly enabled hosted Live mode or completed host-performance validation.

The visual reference is the local dashboard's away/center/home scoreboard and
bundled SVG logos, plus the replay chart's blue/gold solid lines, period context
and compact analysis sections. Heavy dashboard code is not imported for styling.
The preview reuses local logo assets and the replay clock formatter instead.

The responsive scoreboard keeps both teams in one row, with raw pregame records,
scores, snapshot period/clock and win probabilities. All dynamic HTML text is
escaped; logo paths are selected from bundled NBA metadata and embedded locally.
No third-party image request or arbitrary asset path is accepted. A last play
at0:00 is labelled SNAPSHOT, not inferred FINAL. Predictions are unchanged—even
when the frozen model is not100% on an archived final score.

Game flow uses regulation/OT boundary labels, a subdued50% reference and unified
hover. Both team lines remain solid. Box score and feed details are separate
tabs; Player and Status precede stats so DNPs remain visible on narrow screens.
Text probabilities provide an alternative to color/hover. Stale and possibly
stalled warnings remain prominent; normal feed details are secondary. Preview
controls collapse, but archived date/spoiler/non-live disclosure remains visible.

Automated checks cover local logos/scoreboard markup plus all existing gated
state simulations. No new player-impact panel is fabricated: impact integration
is separate work. Full screen-reader certification and real-feed/host capacity
validation remain open.
