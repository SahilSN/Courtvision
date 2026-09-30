# Courtvision

Courtvision is an NBA game intelligence project that uses play-by-play data and machine learning to estimate win probability, identify major turning points, and reconstruct the story of a game.

The current frozen model is **V7**, a PyTorch MLP developed on the 2024-25 NBA season and evaluated on the full 2025-26 regular season without retraining.

## Current Features

- historical game replay across multiple NBA seasons
- possession-level win probability prediction with frozen V7
- leakage-safe pregame team-strength features
- turning-point detection
- counterfactual Player Win Probability Added (WPA v3)
- shared player credit for assists, steals, and blocks
- multi-play momentum-run detection
- contextual "Why the Game Changed" explanations
- automated Game Story generation
- traditional and advanced box-score views
- calibration and temporal-generalization evaluation
- Streamlit dashboard visualization
- season/date/game calendar navigation
- asynchronous background analysis for expensive features
- persistent warm Player Impact inference service
- current-game polling infrastructure for future live use

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

These generated model artifacts are excluded from Git.

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

This allows the same score differential to matter more late in a game than early.

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

## Historical and Live Modes

Courtvision separates historical replay from live analysis.

### Historical

Historical mode allows the user to choose:

```text
Season
  ↓
Date
  ↓
Game
```

Historical analysis prefers locally generated processed play-by-play and season data when available, falling back to NBA API data only when necessary.

Season game catalogs and completed-game analysis artifacts are cached locally to avoid repeated network requests and recomputation.

Pregame records are reconstructed using only games completed before the selected game, preventing future leakage.

### Live

Live mode is intended only for current games.

It uses:

```python
nba_api.stats.endpoints.playbyplayv3.PlayByPlayV3
```

rather than the NBA live CDN.

The live polling harness is:

```text
src/test_live_polling.py
```

Real live polling will be validated during active preseason or regular-season games.

## Turning Points

Courtvision measures the change in predicted win probability after every game state:

```text
probabilityChange =
currentWinProbability
-
previousWinProbability
```

The largest positive changes become home-team turning points.

The largest negative changes become away-team turning points.

The dashboard displays:

- game clock
- play description
- probability before the event
- probability after the event
- probability-point swing

## Dashboard

The Streamlit dashboard currently includes:

- historical/live mode separation
- season selection
- calendar-based game selection
- team logos and team-specific visual styling
- pregame records
- current or final score
- dual-team win-probability chart
- biggest turning points
- Player Impact / WPA leaders
- momentum runs
- contextual "Why the Game Changed" analysis
- automated Game Story
- traditional and advanced box scores
- starter / bench filtering
- expandable prediction timeline
- asynchronous analysis loading
- live refresh controls

Run it with:

```bash
streamlit run dashboard/app.py
```

## Performance Architecture

Courtvision separates expensive computation from the main Streamlit render path.

### Historical analysis

Completed historical games use local processed play-by-play whenever available. Frozen V7 model artifacts and season tables are cached in-process, while reusable historical analysis results and season game catalogs are persisted under:

```text
data/cache/
```

These runtime caches are excluded from Git.

### Player Impact

Player Impact uses the frozen WPA v3 attribution system.

The optimized pipeline includes:

- batched same-time counterfactual V7 inference
- shared-credit row construction without repeated pandas Series mutation
- vectorized sequence-attribution candidate classification
- persistent background inference service
- in-memory reuse of the frozen V7 model and scaler
- lazy per-season training-table caching
- asynchronous dashboard polling

The persistent service is started automatically with Courtvision and remains alive across game requests.

A warm 2025-26 Player Impact request currently takes approximately 0.47 seconds for the core WPA computation on the development machine, compared with roughly 3.2-3.4 seconds for the earlier one-process-per-request path.

### Box scores

Historical box scores are loaded asynchronously when a cached result is unavailable. This prevents slow NBA API responses from blocking the rest of the dashboard.

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
│   └── cache/                  # generated runtime cache
├── models/
├── results/
├── src/
│   ├── analysis.py
│   ├── box_score.py
│   ├── contextual_explanations.py
│   ├── evaluate_calibration.py
│   ├── evaluate_frozen_v7.py
│   ├── feature_engineering.py
│   ├── fetch_play_by_play.py
│   ├── fetch_season.py
│   ├── fetch_team_logos.py
│   ├── game_catalog.py
│   ├── game_story.py
│   ├── live_analysis.py
│   ├── model.py
│   ├── momentum.py
│   ├── player_impact.py
│   ├── predict_game.py
│   ├── preprocess.py
│   ├── run_box_score_worker.py
│   ├── run_player_impact_service.py
│   ├── shared_attribution.py
│   ├── team_metadata.py
│   ├── test_live_polling.py
│   ├── train_baseline.py
│   ├── train_mlp.py
│   ├── validate_fake_live.py
│   └── validate_game_story.py
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

## Data Pipeline

Fetch a season:

```bash
python3 src/fetch_season.py \
    --season 2025-26
```

Run a small pilot:

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

Calibration figures are saved in:

```text
results/calibration_v4_vs_v7.png
results/calibration_v4_vs_v7_game_balanced.png
```

## Frozen Temporal Evaluation

Run the 2025-26 frozen evaluation with:

```bash
python3 src/evaluate_frozen_v7.py \
    --season 2025-26
```

Outputs:

```text
results/v7_2025-26_temporal_metrics.csv
results/v7_2025-26_predictions.csv
```

The prediction file is intentionally ignored by Git because of its size.

## Fake-Live Validation

Run:

```bash
PYTHONPATH=src python3 src/validate_fake_live.py
```

The live-compatible pipeline should reproduce historical V7 predictions up to floating-point precision.

## Live Polling Test

During an active NBA game:

```bash
python3 src/test_live_polling.py \
    <GAME_ID> \
    --interval 15 \
    --max-polls 40
```

A successful test should show new play-by-play states appearing across polls.

## Design Principles

Courtvision follows several modeling rules:

- no future leakage
- chronological evaluation
- probability quality over raw classification accuracy
- frozen future-season testing before further tuning
- historical and live modes remain separate
- frozen analytical components are not changed without validation
- expensive derived intelligence should be reusable rather than recomputed
- dashboard responsiveness should not depend on slow external API requests

The main evaluation metrics are:

- log loss
- Brier score
- AUC
- calibration
- accuracy

## Roadmap

### Completed foundation

```text
Frozen V7 win probability
        ↓
Turning Points
        ↓
Player Impact / WPA v3
        ↓
Momentum v1
        ↓
Contextual Explanations v1
        ↓
Automated Game Story v1
        ↓
Performance + background-computation architecture
```

### Current development direction

```text
Season Intelligence
        ↓
Team Courtvision Rating v1
        ↓
Opponent-adjusted game evaluation
        ↓
Game-by-game rating history
        ↓
Player Courtvision Rating
        ↓
Clutch Intelligence
        ↓
Run-Level Player Attribution
        ↓
Game Shape / Comeback Anatomy
        ↓
Real live end-to-end validation
```

### Additional planned infrastructure

- backfill Player Impact support for prior NBA seasons
- generate compatible historical season training datasets
- validate frozen V7 / WPA v3 behavior season-by-season
- show an intentional unavailable state for seasons without Player Impact coverage
- enable live Player Impact only after real-game validation
- consider V8 only if future evidence shows a meaningful improvement over frozen V7

The longer-term goal is for Courtvision to explain:

```text
what changed,
when it changed,
who caused it,
why it mattered,
and what it says about teams and players over time.
```

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

Large NBA datasets and generated model artifacts are intentionally excluded from source control.

The repository contains the code needed to reproduce the ingestion, preprocessing, modeling, evaluation, replay, and dashboard pipelines.
