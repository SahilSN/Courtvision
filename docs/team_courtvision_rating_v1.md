# Team Courtvision Rating v1

Status: **FROZEN SPECIFICATION**

This document defines the first version of Courtvision Season Intelligence's
team-strength rating system.

The specification should not be changed during implementation unless validation
reveals a concrete issue that requires revisiting the design.

---

## Purpose

Team Courtvision Rating is a dynamic, opponent-adjusted measure of team strength.

It is intended to answer:

> Based on everything this team has done so far this season, how strong has its
> performance been relative to its opponents?

It is distinct from Frozen V7.

Frozen V7 answers:

> Given the current state of one game, what is the probability the home team wins?

Team Courtvision Rating aggregates season-long team performance and must not
become an input to Frozen V7 unless a future V8 is separately developed and
validated.

---

## Initial Rating

Every team begins a season at:

R_0 = 1500

No preseason priors or previous-season carryover are used in v1.

Ratings during approximately the first 10 games may be presented as
**provisional**.

---

## Pregame Expectation

For a home team H playing away team A:

E_H = 1 / (1 + 10^(-((R_H + HCA) - R_A) / 400))

E_A = 1 - E_H

where:

- R_H = home-team rating before the game
- R_A = away-team rating before the game
- HCA = home-court advantage in rating points

HCA will be estimated using the 2024-25 development season and then frozen.

Opponent strength therefore enters the system through pregame rating difference.

---

## Game Result

For the home team:

Y_H = 1 for a win
Y_H = 0 for a loss

The basic rating surprise is:

S_H = Y_H - E_H

A win must always produce a positive rating update.

A loss must always produce a negative rating update.

Margin and game control affect the magnitude of the update, not its sign.

---

## Courtvision Dominance Score

Each game receives a dominance score:

D = w_M * D_M + w_W * D_W

with:

w_M + w_W = 1

The initial v1 design uses two components:

1. final-margin dominance
2. V7 win-probability control

The weights are tuning parameters and are not assumed to be optimal in advance.

---

## Margin Dominance

For the winning team:

m = absolute final point differential

D_M = tanh(m / M)

where M is a margin-saturation parameter.

The transform intentionally has diminishing returns so that extremely large
blowouts do not dominate the rating system.

---

## Win-Probability Control

Let p_t be the eventual winner's Frozen V7 win probability at game state t.

Winner control is calculated as a time-weighted average:

p_bar_W =
    sum(p_t * delta_t)
    /
    sum(delta_t)

where delta_t is the amount of game time represented by that state.

Then:

D_W = clip(2 * (p_bar_W - 0.5), 0, 1)

This measures how much of the game the eventual winner controlled according to
Frozen V7.

Time weighting is required so that high event density does not give some game
segments disproportionate influence.

---

## Dominance Multiplier

Dominance changes the magnitude of the Elo-style update:

F_D = 1 + alpha * D

where alpha controls the maximum effect of dominance.

---

## Rating Update

For the home team:

Delta_R_H =
    K
    * F_D
    * (Y_H - E_H)

Then:

R_H' = R_H + Delta_R_H

R_A' = R_A - Delta_R_H

The system is therefore zero-sum:

Delta_R_H + Delta_R_A = 0

The league-average rating remains centered around 1500.

---

## Frozen Team Courtvision Rating v1 Parameters

Development was performed chronologically on the 2024-25 regular season.

The frozen Team Courtvision Rating v1 parameters are:

- initial rating: 1500
- Elo scale: 400
- K factor: 30
- home-court advantage: 35 rating points
- margin saturation scale M: 40
- dominance alpha: 1.0
- margin dominance weight: 1.0
- V7 win-probability-control weight: 0.0

The final v1 dominance term is therefore margin-only:

D = tanh(winnerMargin / 40)

and the update multiplier is:

F_D = 1 + D

The final home-team update is:

Delta_R_H = 30 * (1 + tanh(winnerMargin / 40)) * (Y_H - E_H)

V7 win-probability control remains part of the canonical Season Intelligence
dataset and is retained for explanation, game-shape analysis, and future
research. It is not part of the frozen Team Courtvision Rating v1 numerical
update because development experiments did not show enough additional value
over margin dominance to justify the extra term.

### Temporal evaluation

Frozen Standard Elo on 2025-26:

- log loss: 0.606564
- Brier score: 0.209598
- AUC: 0.725671
- accuracy: 0.669106

Frozen Team Courtvision Rating v1 on 2025-26:

- log loss: 0.602090
- Brier score: 0.207745
- AUC: 0.729564
- accuracy: 0.670732

The dominance-aware rating therefore improved all four tracked temporal metrics
relative to the frozen Standard Elo baseline.

## Game Shape Metadata

Game shape is stored for interpretation but is not an additional v1 rating term.

Candidate metadata includes:

- finalMargin
- winnerAvgWinProbability
- winnerMinWinProbability
- winnerMaxWinProbability
- winnerTimeAbove50
- winnerTimeAbove75
- largestWinnerDeficit
- gameShapeLabel

Possible explanatory labels may include:

- wire-to-wire
- controlled win
- competitive win
- late separation
- comeback win
- major comeback
- close finish
- blowout

These labels must not alter the rating unless incorporated into a separately
validated future version.

---

## Parameters

The v1 parameter set is:

theta = {
    K,
    HCA,
    M,
    w_M,
    w_W,
    alpha
}

subject to:

w_M + w_W = 1

The parameter set must remain intentionally small and interpretable.

---

## Development and Validation

### Development season

2024-25 is used for chronological development.

For each candidate parameter set:

1. process games strictly chronologically;
2. use only ratings available before each game;
3. compute pregame expected win probability;
4. update ratings only after the result;
5. evaluate future-game predictions.

Primary metric:

- log loss

Secondary metrics:

- Brier score
- AUC
- accuracy
- calibration
- rating stability

### Frozen temporal evaluation

Once parameters are selected, Team Courtvision Rating v1 is frozen.

The frozen system is then evaluated on the 2025-26 season without retuning.

---

## Frozen Standard Elo Baseline Parameters

Stage 2 development was performed chronologically on the 2024-25 regular season.

The frozen Standard Elo v1 parameters are:

```text
Initial rating:           1500
Elo scale:                 400
K factor:                   30
Home-court advantage:       35 rating points
```

Parameter selection criterion:

- primary: chronological pregame log loss
- secondary: Brier score, AUC, accuracy, calibration, stability

Best 2024-25 development metrics:

```text
Log loss:         0.619133
Brier score:      0.215549
AUC:              0.704685
Accuracy:         0.660163
Mean prediction:  0.544461
Home win rate:    0.543902
```

These Standard Elo parameters are frozen before evaluation on 2025-26.

## Required Baselines

Team Courtvision Rating must be compared against:

### Baseline 1
Pregame season win percentage.

### Baseline 2
Standard Elo:

Delta_R = K * (Y - E)

with no Courtvision dominance multiplier.

### Candidate
Team Courtvision Rating v1:

Delta_R =
    K
    * (1 + alpha * D)
    * (Y - E)

Courtvision dominance should be retained only if validation supports its use.

---

## Canonical Game-Level Dataset

Before rating implementation, Stage 1 produces one canonical row per game.

Required fields include:

- gameId
- gameDate
- season
- homeTeam
- awayTeam
- homeScore
- awayScore
- winner
- homeWin
- finalMargin
- winnerMargin
- winnerAvgWinProbability
- winnerMinWinProbability
- winnerMaxWinProbability
- winnerTimeAbove50
- winnerTimeAbove75
- largestWinnerDeficit

Derived rating fields will later include:

- homeRatingBefore
- awayRatingBefore
- homeExpectedWinProb
- awayExpectedWinProb
- marginDominance
- wpControlDominance
- dominanceScore
- dominanceMultiplier
- homeRatingChange
- awayRatingChange
- homeRatingAfter
- awayRatingAfter

The canonical Stage 1 dataset must be deterministic and auditable.

---

## Season-Level Team Output

For each team, Courtvision should eventually expose:

- team
- gamesPlayed
- wins
- losses
- currentRating
- ratingRank
- peakRating
- lowestRating
- ratingChangeLast5
- ratingChangeLast10

Later extensions may add:

- averageOpponentRating
- strengthOfSchedule
- qualityWins
- badLosses
- dominantWins
- closeGameRecord

These are not part of the v1 core update rule.

---

## Implementation Stages

### Stage 1 — Canonical game-level intelligence dataset
Generate one row per game containing result, margin, and time-weighted Frozen V7
game-control features.

### Stage 2 — Standard Elo baseline
Implement sequential pregame ratings and expected win probabilities.

### Stage 3 — Courtvision Rating engine
Add margin dominance and V7 control dominance.

### Stage 4 — Parameter validation
Tune chronologically on 2024-25, freeze, and evaluate on 2025-26.

### Stage 5 — Season Intelligence UI
Add leaderboard, team rating history, game-by-game changes, and explanations.

---

## Frozen v1 Equations

Pregame expectation:

E_H =
    1
    /
    (1 + 10^(-((R_H + HCA) - R_A) / 400))

Margin dominance:

D_M = tanh(abs(finalMargin) / M)

Winner V7 control:

D_W = clip(2 * (winnerAvgWinProbability - 0.5), 0, 1)

Combined dominance:

D = w_M * D_M + w_W * D_W

Dominance multiplier:

F_D = 1 + alpha * D

Home rating update:

Delta_R_H =
    K
    * F_D
    * (Y_H - E_H)

Postgame ratings:

R_H' = R_H + Delta_R_H

R_A' = R_A - Delta_R_H
