# Courtvision

Courtvision is an NBA game-intelligence platform that combines play-by-play data, machine learning, player attribution, and season-level ratings to explain how games change, who drives those changes, and what those results say about teams over time.

The current frozen win-probability model is **V7**, a PyTorch MLP developed on the 2024-25 NBA regular season and evaluated on the complete 2025-26 regular season without retraining.

Courtvision supports three primary workflows:

- **Historical** — analyze completed NBA games
- **Live** — follow a current game as play-by-play arrives
- **Season Intelligence** — explore Team Courtvision Rating histories, league rankings, and game-level rating explanations

## Current Features

### Game Intelligence

- possession-level win-probability prediction with frozen V7
- leakage-safe pregame team-strength features
- turning-point detection
- counterfactual Player Win Probability Added (**WPA v3**)
- shared player credit for assists, steals, and blocks
- multi-play **Momentum v1** run detection
- contextual **Why the Game Changed** explanations
- automated **Game Story** generation
- traditional and advanced box scores

### Live Intelligence

- ScoreboardV3 current-game discovery
- PlayByPlayV3 live ingestion
- automatic refresh controls
- live win-probability inference
- Live Player Impact
- live player stint reconstruction
- live box-score reconstruction
- overtime-aware game state
- authoritative scheduled / live / final lifecycle status
- last-valid-state retention after temporary refresh failures
- graceful handling of incomplete early-game play-by-play
- component-level failure isolation

### Season Intelligence

- frozen **Team Courtvision Rating v1**
- historical rating backfills from 2019-20 through 2025-26
- 30-team league leaderboard
- current, peak, and lowest team ratings
- season rating change
- Last 5 and Last 10 rating movement
- league risers and fallers
- game-by-game rating trajectory
- league rank after each game
- Last 10 / Last 20 / full-season game logs
- per-game **Why Did the Rating Change?** explanations
- incremental rating infrastructure for the current season

## Model

Courtvision V7 uses a small multilayer perceptron implemented in PyTorch.

Architecture:

```text
8 inputs
  ↓
Linear(8, 16)
ReLU
  ↓
Linear(16, 8)
ReLU
  ↓
Linear(8, 1)
```

Training uses:

- `BCEWithLogitsLoss`
- Adam
- learning rate `0.001`
- batch size `64`
- early stopping
- `StandardScaler` fit only on the training split

Model artifacts:

```text
models/win_probability_mlp_v7.pt
models/win_probability_scaler_v7.pkl
```

The frozen V7 production model and scaler are tracked for deployment; other generated model artifacts remain excluded from Git.

## V7 Features

```python
MODEL_FEATURES = [
    "elapsedGameTime",
    "homeScoreDiff",
    "homePossession",
    "totalScore",
    "homePreGameWinPct",
    "awayPreGameWinPct",
    "strengthDifference",
    "scoreDiffLateWeight",
]
```

### Feature overview

- `elapsedGameTime`: seconds elapsed in the game
- `homeScoreDiff`: home score minus away score
- `homePossession`: 1 for home possession, 0 for away possession
- `totalScore`: total points scored by both teams
- `homePreGameWinPct`: home team's record entering the game
- `awayPreGameWinPct`: away team's record entering the game
- `strengthDifference`: home pregame win percentage minus away pregame win percentage
- `scoreDiffLateWeight`: score differential weighted by game progress

The final interaction feature is:

```text
homeScoreDiff * clip(elapsedGameTime / 2880, 0, 1)
```

This allows the same score differential to carry more information late in a game than early.

## Evaluation

### 2024-25 chronological validation

V7 was selected using a chronological 80/20 split of the 2024-25 regular season.

State-weighted results:

| Metric | V7 |
|---|---:|
| Accuracy | 0.7813 |
| Log loss | 0.4302 |
| Brier score | 0.1424 |
| AUC | 0.8794 |
| ECE | 0.0325 |

Game-balanced results:

| Metric | V7 |
|---|---:|
| Log loss | 0.4244 |
| Brier score | 0.1403 |
| AUC | 0.8831 |
| ECE | 0.0340 |

### 2025-26 frozen temporal evaluation

After V7 was frozen, it was evaluated on the complete 2025-26 regular season without retraining, rescaling, feature changes, threshold tuning, or architecture changes.

Evaluation set:

```text
Games: 1,230
Game states: 619,328
```

State-weighted results:

| Metric | 2025-26 |
|---|---:|
| Accuracy | 0.7746 |
| Log loss | 0.4506 |
| Brier score | 0.1501 |
| AUC | 0.8629 |
| ECE | 0.0160 |

Game-balanced results:

| Metric | 2025-26 |
|---|---:|
| Accuracy | 0.7776 |
| Log loss | 0.4459 |
| Brier score | 0.1483 |
| AUC | 0.8661 |
| ECE | 0.0165 |

Detailed results are stored in:

```text
results/v7_2025-26_temporal_metrics.csv
```

## Historical Mode

Historical mode allows the user to choose:

```text
Season
  ↓
Date
  ↓
Game
```

Completed games prefer locally generated processed play-by-play and cached analysis artifacts when available.

Season catalogs and immutable historical analyses are cached so repeated dashboard sessions do not require unnecessary NBA API calls or V7 recomputation.

Pregame records are reconstructed using only games completed before the selected game, preventing future leakage.

Historical replay can also reproduce intermediate game states such as:

- end of Q1
- halftime
- end of Q3
- selected Q4 states
- overtime periods
- final

This allows the live-compatible stack to be tested against completed games.

## Live Mode

Live mode is designed for the current NBA season.

### Game discovery

Courtvision uses:

```python
nba_api.stats.endpoints.scoreboardv3.ScoreboardV3
```

for scheduled, live, and completed games on the current date.

ScoreboardV3 provides the game ID, matchup, team IDs, game clock, lifecycle state, and final status needed by the dashboard.

### Play-by-play

Once a game is selected, Courtvision uses:

```python
nba_api.stats.endpoints.playbyplayv3.PlayByPlayV3
```

to retrieve the latest play-by-play state.

The live pipeline then:

```text
ScoreboardV3
      ↓
Game ID
      ↓
PlayByPlayV3
      ↓
Preprocessing
      ↓
Pregame context
      ↓
Frozen V7 inference
      ↓
Turning Points / WPA / Momentum
      ↓
Live dashboard
```

### Live resilience

The live dashboard is designed to degrade gracefully.

If a refresh fails after a valid state has already loaded, Courtvision preserves and displays the most recent successful game state.

If an early live feed does not yet contain enough information to reconstruct a valid game state, Courtvision waits rather than treating the feed as a fatal error.

ScoreboardV3 is used separately for authoritative lifecycle semantics such as:

```text
Scheduled
Live
Final
Final/OT
Final/OT2
```

## Preseason Live Validation

The 2026-27 live pipeline is currently configured for preseason system validation.

Preseason support includes:

- ScoreboardV3 scheduled-game discovery
- `Pre Season` propagation through live analysis
- preseason-specific pregame team records
- separation from local regular-season pregame context
- season-type-aware last-valid-state caching
- isolated preseason Team Courtvision Rating runtime support
- protection against publishing preseason ratings into production Season Intelligence artifacts

The October 3, 2026 preseason game:

```text
MIA @ TOR
Game ID: 0012600009
```

has been successfully discovered through the ScoreboardV3 live-game path.

The remaining preseason milestone is real end-to-end validation while the game is active.

Preseason is being used to validate the **live system**, not to re-evaluate or tune frozen V7 model quality.

## Turning Points

Courtvision measures the change in predicted win probability after every usable game state:

```text
probabilityChange =
currentWinProbability
-
previousWinProbability
```

The largest positive and negative changes identify the most important swings for each team.

The dashboard displays:

- game clock
- play description
- probability before the event
- probability after the event
- probability-point swing

## Player Impact / WPA v3

Player Impact measures how individual players contributed to changes in win probability.

WPA v3 uses counterfactual attribution rather than assigning the entire swing to the player directly associated with the final play.

The attribution system includes:

- scorer attribution
- assist credit
- steal credit
- block credit
- shared-credit handling
- same-time event reconstruction
- batched counterfactual V7 inference

The dashboard exposes Player Impact in both historical and live-compatible workflows.

## Momentum v1

Momentum identifies meaningful multi-play runs rather than treating isolated possessions as complete runs.

The current presentation selects up to **three momentum runs per team**.

Runs are evaluated using features such as:

- win-probability swing
- score-margin swing
- duration
- overlap with stronger candidate runs

The validation suite checks structural correctness and run-selection behavior across sampled games.

## Season Intelligence

Season Intelligence extends Courtvision from individual games to team performance over an entire season.

### Team Courtvision Rating v1

Team Courtvision Rating is a frozen, chronological, zero-sum rating system.

Each game begins with pregame ratings for both teams. The update depends on:

- expected result
- actual winner
- winner margin
- Courtvision dominance multiplier

The dashboard currently provides two Season Intelligence views.

### League Overview

League Overview includes:

- No. 1 rated team
- full NBA rating leaderboard
- team records
- current ratings
- Last 5 movement
- Last 10 movement
- season-long rating change
- biggest recent risers
- biggest recent fallers

### Team Explorer

Team Explorer includes:

- team selector
- current NBA rating rank
- record
- current rating
- peak rating
- lowest rating
- season rating change
- complete rating trajectory
- Last 5 and Last 10 movement
- largest single-game gain
- largest single-game loss
- configurable game log
- per-game rating explanation

The game log supports:

```text
Last 10
Last 20
All Games
```

The rating-explanation selector follows the same selected scope.

## Dashboard

The Streamlit dashboard has three primary modes:

```text
Historical
Live
Season Intelligence
```

Across those modes, the dashboard includes:

- season/date/game navigation
- ScoreboardV3 current-game discovery
- team logos and team-specific visual styling
- pregame records
- current or final score
- dual-team win-probability chart
- turning points
- Player Impact / WPA leaders
- momentum runs
- contextual game explanations
- automated Game Story
- traditional and advanced box scores
- starter / bench filtering
- live stint reconstruction
- expandable prediction timeline
- historical live replay
- live refresh controls
- League Overview
- Team Explorer

Run the dashboard with:

```bash
streamlit run dashboard/app.py
```

## Production Hardening

Courtvision includes several safeguards for live and historical reliability.

### Component isolation

Major dashboard components are rendered independently so a failure in one derived analysis does not necessarily take down the rest of the game view.

### Last-valid live state

Successful live analyses are cached in Streamlit session state.

If a later API refresh fails, the dashboard can continue displaying the most recent valid state for the same:

- game
- season
- season type
- replay configuration

### Incomplete play-by-play

Early or partially populated PBP feeds raise a dedicated not-ready state rather than a generic processing failure.

### Lifecycle correctness

True-live games use ScoreboardV3 for authoritative final-state detection instead of inferring game completion from a Q4 clock alone.

This avoids incorrectly labeling a tied regulation game as final before overtime begins.

## Validation

### Replay box score

The replay box-score validator currently reproduces:

```text
4,872 / 4,872 exact tracked stat cells
20 / 20 sampled games
0 unmatched player rows
0 failed games
```

Tracked statistics include:

- PTS
- REB
- AST
- STL
- BLK
- TO
- FGM
- FGA
- 3PM
- 3PA
- FTM
- FTA

### Momentum

The current sampled Momentum v1 regression suite reports:

```text
10 / 10 games PASS
0 structural failures
0 manual-review flags
```

## Performance Architecture

Courtvision separates expensive computation from the primary Streamlit render path.

### Historical analysis

Completed historical games use local processed play-by-play whenever available.

Frozen V7 artifacts and season tables are cached in-process, while reusable historical analysis and season-game catalogs are persisted under:

```text
data/cache/
```

Runtime caches are excluded from Git.

### Player Impact

The Player Impact pipeline includes:

- batched same-time counterfactual V7 inference
- shared-credit row construction
- vectorized sequence-attribution candidate classification
- persistent background inference service
- in-memory reuse of the frozen V7 model and scaler
- lazy per-season training-table caching
- asynchronous dashboard polling

### Box scores

Historical box scores can be loaded asynchronously so slow NBA API responses do not block unrelated dashboard components.

## Project Structure

```text
Courtvision/
├── dashboard/
│   ├── app.py
│   └── assets/
│       └── logos/
├── data/
│   ├── raw/
│   ├── processed/
│   ├── training/
│   └── cache/
├── docs/
├── models/
├── results/
│   ├── season_intelligence/
│   └── team_rating/
├── src/
│   ├── analysis.py
│   ├── backfill_historical_seasons.py
│   ├── backfill_season_intelligence.py
│   ├── box_score.py
│   ├── contextual_explanations.py
│   ├── courtvision_rating.py
│   ├── evaluate_calibration.py
│   ├── evaluate_frozen_v7.py
│   ├── feature_engineering.py
│   ├── fetch_play_by_play.py
│   ├── fetch_season.py
│   ├── fetch_team_logos.py
│   ├── game_catalog.py
│   ├── game_story.py
│   ├── incremental_team_rating.py
│   ├── live_analysis.py
│   ├── live_stints.py
│   ├── model.py
│   ├── momentum.py
│   ├── player_impact.py
│   ├── predict_game.py
│   ├── preprocess.py
│   ├── replay_box_score.py
│   ├── run_box_score_worker.py
│   ├── run_player_impact_service.py
│   ├── season_intelligence.py
│   ├── shared_attribution.py
│   ├── team_metadata.py
│   ├── team_rating.py
│   ├── team_season_intelligence.py
│   ├── train_baseline.py
│   ├── train_mlp.py
│   ├── update_live_season.py
│   ├── validate_incremental_team_rating.py
│   ├── validate_momentum.py
│   └── validate_replay_box_score.py
├── README.md
├── requirements.txt
└── .gitignore
```

## Setup

Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the dashboard:

```bash
streamlit run dashboard/app.py
```

## Data Pipeline

Fetch a regular season:

```bash
python3 src/fetch_season.py \
    --season 2025-26
```

Run a smaller pilot:

```bash
python3 src/fetch_season.py \
    --season 2025-26 \
    --max-games 10 \
    --output-suffix _pilot
```

Generated NBA datasets are excluded from Git.

## Training

Train the PyTorch MLP with:

```bash
python3 src/train_mlp.py
```

The current frozen production model is V7.

## Calibration

Run calibration evaluation with:

```bash
python3 src/evaluate_calibration.py
```

Calibration figures are written under `results/`.

## Frozen Temporal Evaluation

Run the 2025-26 frozen evaluation with:

```bash
python3 src/evaluate_frozen_v7.py \
    --season 2025-26
```

Generated prediction outputs may be excluded from Git because of their size.

## Validation Commands

Replay box-score regression:

```bash
PYTHONPATH=src python3 \
    src/validate_replay_box_score.py \
    --count 20
```

Momentum regression:

```bash
PYTHONPATH=src python3 \
    src/validate_momentum.py \
    --season 2024-25 \
    --sample-size 10
```

Static integrity:

```bash
git diff --check
python -m compileall -q src dashboard
```

## Live Season Updates

The live-season updater supports both regular-season production use and isolated preseason testing.

Regular-season production is the default:

```bash
PYTHONPATH=src python3 \
    src/update_live_season.py \
    --season 2026-27
```

Preseason rating experiments must use an isolated runtime and must not publish into the production Season Intelligence directory unless an explicitly separate publish directory is provided.

For a no-write preseason discovery check:

```bash
PYTHONPATH=src python3 \
    src/update_live_season.py \
    --season 2026-27 \
    --season-type "Pre Season" \
    --dry-run
```

## Design Principles

Courtvision follows several modeling and engineering rules:

- no future leakage
- chronological evaluation
- probability quality over raw classification accuracy
- frozen future-season testing before further model tuning
- frozen analytical components are not modified without validation
- preseason testing validates the live system rather than tuning V7
- historical replay and true-live operation remain explicitly separated
- expensive derived intelligence should be reusable rather than recomputed
- slow external APIs should not take down unrelated dashboard components
- live failures should preserve the most recent valid state where safe
- preseason data must remain isolated from regular-season production ratings

Primary model-evaluation metrics include:

- log loss
- Brier score
- AUC
- calibration
- accuracy

## Roadmap

### Completed

```text
Frozen V7 Win Probability
        ↓
Turning Points
        ↓
Player WPA v3
        ↓
Momentum v1
        ↓
Contextual Explanations
        ↓
Game Story
        ↓
Team Courtvision Rating v1
        ↓
Season Intelligence Backend
        ↓
Live / Replay Infrastructure
        ↓
Production Hardening
        ↓
Season Intelligence UI v2
        ↓
Preseason Live Readiness
```

### Immediate milestone

**October 3, 2026 — real preseason live validation**

The MIA @ TOR preseason game will be used to test the complete live system while an NBA game is actually in progress.

The validation target includes:

- scheduled → live transition
- first usable play-by-play
- correct home/away identity
- V7 probability updates
- turning points
- momentum
- Player WPA
- live box score
- stint reconstruction
- refresh behavior
- temporary API failure handling
- quarter / overtime state
- authoritative final status

### Next major development phase

**Player Courtvision Rating**

The next major analytical feature will extend Courtvision's player-level game attribution into a season-level player rating.

Planned work includes:

- define the player-rating objective
- determine how Player WPA and opportunity should contribute
- contextual normalization
- historical backfill
- validation
- player season summaries
- NBA player leaderboard
- dashboard integration

### Later exploration

Potential later additions include:

- game-control season analytics
- comeback / deficit profiles
- time above 50% / 75% win probability
- game-shape analysis
- clutch intelligence
- run-level player attribution
- additional player and team cross-navigation

A V8 win-probability model should only be considered if future evidence shows a meaningful improvement over frozen V7.

## Tech Stack

- Python
- PyTorch
- pandas
- NumPy
- scikit-learn
- nba_api
- Streamlit
- Plotly
- Matplotlib

## Notes

Large NBA datasets, runtime caches, and generated model artifacts are intentionally excluded from source control.

The repository contains the code required for Courtvision's ingestion, preprocessing, modeling, evaluation, historical replay, live analysis, player attribution, team-rating, Season Intelligence, validation, and dashboard pipelines.
