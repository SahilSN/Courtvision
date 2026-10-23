# Player Courtvision Rating — Design Contract

## Objective

Player Courtvision Rating should measure a player's accumulated, contextual
impact on winning over time. It is a season-level companion to game-level WPA
v3, not a replacement for WPA and not a generic box-score composite.

The first version should answer:

> Given the opportunities this player received, how consistently did their
> attributed actions improve or reduce their team's chance of winning?

## Separation of concepts

- **Player WPA v3:** what changed because of a player's attributed events in
  one game.
- **Player Courtvision Rating:** what the player's game-level impact says over
  a growing body of games.
- **Traditional production:** descriptive context, not a substitute for
  Courtvision impact.

## Phase 1 dataset contract

One row represents one player appearance in one completed game. Every player
with positive minutes must be present, including players with no attributed
WPA events.

Required identity and context:

- season, game date, and canonical game ID
- player ID and full player name
- team and opponent
- home/away and win/loss
- starter flag
- minutes and, when available, possessions

Frozen impact inputs:

- attributed event count
- net, positive, negative, and absolute WPA
- largest positive and negative attributed event

Traditional box-score fields may be retained for diagnostics, but the first
rating formula must not quietly become a conventional box-score rating.

## Rating principles

1. Preserve frozen WPA v3 and shared-credit attribution.
2. Include zero-event appearances rather than selecting only visible events.
3. Adjust for opportunity using minutes or possessions.
4. Shrink small samples toward a neutral population prior.
5. Separate full-season level from recent form.
6. Update chronologically and prohibit future leakage.
7. Keep game-level rating changes explainable.
8. Treat team changes as continuity for the player, while retaining team
   context on every game row.

## Candidate outputs

- current, peak, and lowest rating
- season rating change
- games and minutes
- Last 5 and Last 10 movement
- average and cumulative WPA
- opportunity-adjusted WPA
- largest single-game gain and loss
- player rank and team roster rank

## Validation gates before dashboard integration

- no duplicate player-game rows
- every positive-minute player represented
- WPA totals reproduce frozen game summaries
- zero-event players remain in the dataset with zero WPA
- chronological reruns are deterministic
- small-sample leaders are visibly shrunk
- rankings are not dominated solely by minutes or one high-leverage event
- reasonable stability across adjacent season windows
- measurable relationship with future game impact

## Development sequence

1. Build and validate the player-game dataset.
2. Backfill a representative historical sample.
3. Compare opportunity normalization and shrinkage candidates.
4. Freeze Player Courtvision Rating v1.
5. Backfill completed historical seasons.
6. Add incremental current-season updates.
7. Build the player leaderboard and player profile UI.
