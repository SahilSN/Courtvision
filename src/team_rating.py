from __future__ import annotations

import argparse
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)


ROOT_DIR = (
    Path(__file__)
    .resolve()
    .parents[1]
)

SEASON_INTELLIGENCE_DIR = (
    ROOT_DIR
    / "results"
    / "season_intelligence"
)

RATING_RESULTS_DIR = (
    ROOT_DIR
    / "results"
    / "team_rating"
)

INITIAL_RATING = 1500.0
ELO_SCALE = 400.0


# ============================================================
# Data
# ============================================================

def load_game_features(
    season,
):
    path = (
        SEASON_INTELLIGENCE_DIR
        / f"{season}_game_features_v1.csv"
    )

    if not path.exists():
        raise FileNotFoundError(
            "Missing frozen Stage 1 Season Intelligence "
            f"dataset: {path}"
        )

    df = pd.read_csv(
        path,
        dtype={
            "gameId":
                str,
        },
    )

    df[
        "_sortDate"
    ] = pd.to_datetime(
        df[
            "gameDate"
        ],
        errors="coerce",
    )

    if df[
        "_sortDate"
    ].isna().any():
        raise ValueError(
            "One or more games have invalid gameDate values."
        )

    df = (
        df
        .sort_values(
            [
                "_sortDate",
                "gameId",
            ],
            kind="mergesort",
        )
        .drop(
            columns=[
                "_sortDate",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    return df


# ============================================================
# Elo math
# ============================================================

def expected_home_win_probability(
    home_rating,
    away_rating,
    home_court_advantage,
):
    rating_difference = (
        (
            float(
                home_rating
            )
            + float(
                home_court_advantage
            )
        )
        - float(
            away_rating
        )
    )

    return float(
        1.0
        / (
            1.0
            + 10.0 ** (
                -rating_difference
                / ELO_SCALE
            )
        )
    )


# ============================================================
# Sequential standings baseline
# ============================================================

def pregame_win_pct(
    wins,
    losses,
):
    games = (
        int(
            wins
        )
        + int(
            losses
        )
    )

    if games == 0:
        return 0.5

    return float(
        wins
        / games
    )


def standings_expected_home_win_probability(
    home_win_pct,
    away_win_pct,
):
    """
    Simple record-only baseline.

    Normalize the two pregame win percentages into a
    matchup probability.

    If both teams are 0-0 or otherwise produce a zero
    denominator, return 50%.
    """

    home = float(
        home_win_pct
    )

    away = float(
        away_win_pct
    )

    denominator = (
        home
        + away
    )

    if denominator <= 0:
        return 0.5

    return float(
        home
        / denominator
    )


# ============================================================
# Season simulation
# ============================================================

def run_standard_elo(
    games,
    k_factor,
    home_court_advantage,
    initial_rating=INITIAL_RATING,
):
    ratings = defaultdict(
        lambda:
            float(
                initial_rating
            )
    )

    wins = defaultdict(
        int
    )

    losses = defaultdict(
        int
    )

    peak_ratings = defaultdict(
        lambda:
            float(
                initial_rating
            )
    )

    low_ratings = defaultdict(
        lambda:
            float(
                initial_rating
            )
    )

    rows = []

    for _, game in (
        games.iterrows()
    ):
        home_team = str(
            game[
                "homeTeam"
            ]
        )

        away_team = str(
            game[
                "awayTeam"
            ]
        )

        home_rating_before = float(
            ratings[
                home_team
            ]
        )

        away_rating_before = float(
            ratings[
                away_team
            ]
        )

        home_expected = (
            expected_home_win_probability(
                home_rating=(
                    home_rating_before
                ),
                away_rating=(
                    away_rating_before
                ),
                home_court_advantage=(
                    home_court_advantage
                ),
            )
        )

        home_win = int(
            game[
                "homeWin"
            ]
        )

        rating_change = float(
            float(
                k_factor
            )
            * (
                float(
                    home_win
                )
                - home_expected
            )
        )

        home_rating_after = (
            home_rating_before
            + rating_change
        )

        away_rating_after = (
            away_rating_before
            - rating_change
        )

        home_win_pct = (
            pregame_win_pct(
                wins[
                    home_team
                ],
                losses[
                    home_team
                ],
            )
        )

        away_win_pct = (
            pregame_win_pct(
                wins[
                    away_team
                ],
                losses[
                    away_team
                ],
            )
        )

        standings_probability = (
            standings_expected_home_win_probability(
                home_win_pct,
                away_win_pct,
            )
        )

        rows.append(
            {
                "season":
                    game[
                        "season"
                    ],

                "gameDate":
                    game[
                        "gameDate"
                    ],

                "gameId":
                    game[
                        "gameId"
                    ],

                "homeTeam":
                    home_team,

                "awayTeam":
                    away_team,

                "homeWin":
                    home_win,

                "homeRatingBefore":
                    home_rating_before,

                "awayRatingBefore":
                    away_rating_before,

                "homeExpectedWinProb":
                    home_expected,

                "awayExpectedWinProb":
                    (
                        1.0
                        - home_expected
                    ),

                "homeRatingChange":
                    rating_change,

                "awayRatingChange":
                    -rating_change,

                "homeRatingAfter":
                    home_rating_after,

                "awayRatingAfter":
                    away_rating_after,

                "homePreGameWins":
                    wins[
                        home_team
                    ],

                "homePreGameLosses":
                    losses[
                        home_team
                    ],

                "awayPreGameWins":
                    wins[
                        away_team
                    ],

                "awayPreGameLosses":
                    losses[
                        away_team
                    ],

                "homePreGameWinPct":
                    home_win_pct,

                "awayPreGameWinPct":
                    away_win_pct,

                "standingsHomeWinProb":
                    standings_probability,
            }
        )

        ratings[
            home_team
        ] = (
            home_rating_after
        )

        ratings[
            away_team
        ] = (
            away_rating_after
        )

        peak_ratings[
            home_team
        ] = max(
            peak_ratings[
                home_team
            ],
            home_rating_after,
        )

        peak_ratings[
            away_team
        ] = max(
            peak_ratings[
                away_team
            ],
            away_rating_after,
        )

        low_ratings[
            home_team
        ] = min(
            low_ratings[
                home_team
            ],
            home_rating_after,
        )

        low_ratings[
            away_team
        ] = min(
            low_ratings[
                away_team
            ],
            away_rating_after,
        )

        if home_win == 1:
            wins[
                home_team
            ] += 1

            losses[
                away_team
            ] += 1

        else:
            wins[
                away_team
            ] += 1

            losses[
                home_team
            ] += 1

    history = pd.DataFrame(
        rows
    )

    all_teams = sorted(
        set(
            ratings.keys()
        )
    )

    standings = pd.DataFrame(
        [
            {
                "team":
                    team,

                "gamesPlayed":
                    (
                        wins[
                            team
                        ]
                        + losses[
                            team
                        ]
                    ),

                "wins":
                    wins[
                        team
                    ],

                "losses":
                    losses[
                        team
                    ],

                "currentRating":
                    float(
                        ratings[
                            team
                        ]
                    ),

                "peakRating":
                    float(
                        peak_ratings[
                            team
                        ]
                    ),

                "lowestRating":
                    float(
                        low_ratings[
                            team
                        ]
                    ),
            }

            for team in all_teams
        ]
    )

    standings = (
        standings
        .sort_values(
            "currentRating",
            ascending=False,
            kind="mergesort",
        )
        .reset_index(
            drop=True
        )
    )

    standings[
        "ratingRank"
    ] = np.arange(
        1,
        len(
            standings
        )
        + 1,
    )

    return (
        history,
        standings,
    )


# ============================================================
# Metrics
# ============================================================

def binary_metrics(
    y_true,
    probability,
):
    y_true = np.asarray(
        y_true,
        dtype=int,
    )

    probability = np.asarray(
        probability,
        dtype=float,
    )

    probability = np.clip(
        probability,
        1e-6,
        1.0 - 1e-6,
    )

    prediction = (
        probability
        >= 0.5
    ).astype(
        int
    )

    return {
        "logLoss":
            float(
                log_loss(
                    y_true,
                    probability,
                    labels=[
                        0,
                        1,
                    ],
                )
            ),

        "brier":
            float(
                brier_score_loss(
                    y_true,
                    probability,
                )
            ),

        "auc":
            float(
                roc_auc_score(
                    y_true,
                    probability,
                )
            ),

        "accuracy":
            float(
                accuracy_score(
                    y_true,
                    prediction,
                )
            ),

        "meanPrediction":
            float(
                probability.mean()
            ),

        "actualHomeWinRate":
            float(
                y_true.mean()
            ),
    }


def evaluate_history(
    history,
):
    elo_metrics = (
        binary_metrics(
            history[
                "homeWin"
            ],
            history[
                "homeExpectedWinProb"
            ],
        )
    )

    standings_metrics = (
        binary_metrics(
            history[
                "homeWin"
            ],
            history[
                "standingsHomeWinProb"
            ],
        )
    )

    return (
        elo_metrics,
        standings_metrics,
    )


# ============================================================
# Development grid
# ============================================================

def tune_standard_elo(
    games,
    k_values=None,
    hca_values=None,
):
    if k_values is None:
        k_values = [
            5,
            10,
            15,
            20,
            25,
            30,
            35,
            40,
            50,
        ]

    if hca_values is None:
        hca_values = list(
            range(
                0,
                101,
                5,
            )
        )

    rows = []

    total = (
        len(
            k_values
        )
        * len(
            hca_values
        )
    )

    index = 0

    for k_factor in (
        k_values
    ):
        for hca in (
            hca_values
        ):
            index += 1

            history, _ = (
                run_standard_elo(
                    games=games,
                    k_factor=k_factor,
                    home_court_advantage=hca,
                )
            )

            elo_metrics, _ = (
                evaluate_history(
                    history
                )
            )

            rows.append(
                {
                    "kFactor":
                        float(
                            k_factor
                        ),

                    "homeCourtAdvantage":
                        float(
                            hca
                        ),

                    **elo_metrics,
                }
            )

    result = pd.DataFrame(
        rows
    )

    result = (
        result
        .sort_values(
            [
                "logLoss",
                "brier",
                "auc",
            ],
            ascending=[
                True,
                True,
                False,
            ],
            kind="mergesort",
        )
        .reset_index(
            drop=True
        )
    )

    return result


# ============================================================
# Validation
# ============================================================

def validate_rating_history(
    history,
    standings,
):
    if history.empty:
        raise ValueError(
            "Rating history is empty."
        )

    if len(
        standings
    ) != 30:
        raise ValueError(
            "Expected 30 NBA teams in final ratings."
        )

    if (
        history[
            "gameId"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate game IDs in rating history."
        )

    conservation = (
        history[
            "homeRatingChange"
        ]
        + history[
            "awayRatingChange"
        ]
    ).abs().max()

    if conservation > 1e-9:
        raise ValueError(
            "Standard Elo is not zero-sum."
        )

    league_mean = float(
        standings[
            "currentRating"
        ].mean()
    )

    if not math.isclose(
        league_mean,
        INITIAL_RATING,
        abs_tol=1e-9,
        rel_tol=0.0,
    ):
        raise ValueError(
            "League-average rating drifted away from 1500."
        )

    if not (
        (
            history[
                "homeExpectedWinProb"
            ]
            > 0
        )
        &
        (
            history[
                "homeExpectedWinProb"
            ]
            < 1
        )
    ).all():
        raise ValueError(
            "Invalid Elo win probabilities."
        )

    expected_sign = np.where(
        history[
            "homeWin"
        ].to_numpy(
            dtype=int
        )
        == 1,
        1,
        -1,
    )

    actual_sign = np.sign(
        history[
            "homeRatingChange"
        ].to_numpy(
            dtype=float
        )
    )

    if not np.array_equal(
        expected_sign,
        actual_sign,
    ):
        raise ValueError(
            "A winner received a negative Elo change "
            "or a loser received a positive Elo change."
        )

    print(
        "✓ Standard Elo validation passed."
    )


# ============================================================
# CLI
# ============================================================

def parse_args():
    parser = (
        argparse.ArgumentParser(
            description=(
                "Courtvision Team Rating — "
                "Stage 2 standard Elo baseline."
            )
        )
    )

    parser.add_argument(
        "--season",
        required=True,
    )

    parser.add_argument(
        "--tune",
        action="store_true",
    )

    parser.add_argument(
        "--k",
        type=float,
        default=None,
    )

    parser.add_argument(
        "--hca",
        type=float,
        default=None,
    )

    return (
        parser.parse_args()
    )


def main():
    args = (
        parse_args()
    )

    games = (
        load_game_features(
            args.season
        )
    )

    RATING_RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if args.tune:
        print(
            "Courtvision Team Rating — "
            "Standard Elo Development"
        )

        print(
            f"Season: {args.season}"
        )

        print(
            f"Games: {len(games):,}"
        )

        print()

        grid = (
            tune_standard_elo(
                games
            )
        )

        grid_path = (
            RATING_RESULTS_DIR
            / (
                f"{args.season}_"
                f"standard_elo_grid_v1.csv"
            )
        )

        grid.to_csv(
            grid_path,
            index=False,
        )

        print(
            "Best parameter sets:"
        )

        print(
            grid.head(
                15
            ).to_string(
                index=False
            )
        )

        print()
        print(
            f"Saved: {grid_path}"
        )

        return

    if (
        args.k is None
        or args.hca is None
    ):
        raise ValueError(
            "--k and --hca are required unless --tune is used."
        )

    history, standings = (
        run_standard_elo(
            games=games,
            k_factor=args.k,
            home_court_advantage=args.hca,
        )
    )

    validate_rating_history(
        history,
        standings,
    )

    elo_metrics, standings_metrics = (
        evaluate_history(
            history
        )
    )

    history_path = (
        RATING_RESULTS_DIR
        / (
            f"{args.season}_"
            f"standard_elo_history_v1.csv"
        )
    )

    standings_path = (
        RATING_RESULTS_DIR
        / (
            f"{args.season}_"
            f"standard_elo_ratings_v1.csv"
        )
    )

    history.to_csv(
        history_path,
        index=False,
    )

    standings.to_csv(
        standings_path,
        index=False,
    )

    print()
    print(
        "Standard Elo"
    )

    print(
        f"K: {args.k:g}"
    )

    print(
        f"HCA: {args.hca:g}"
    )

    print()

    print(
        "Elo metrics:"
    )

    for key, value in (
        elo_metrics.items()
    ):
        print(
            f"  {key}: {value:.6f}"
        )

    print()

    print(
        "Pregame standings baseline:"
    )

    for key, value in (
        standings_metrics.items()
    ):
        print(
            f"  {key}: {value:.6f}"
        )

    print()

    print(
        "Final ratings:"
    )

    print(
        standings[
            [
                "ratingRank",
                "team",
                "wins",
                "losses",
                "currentRating",
                "peakRating",
                "lowestRating",
            ]
        ]
        .head(
            15
        )
        .to_string(
            index=False
        )
    )

    print()
    print(
        f"History: {history_path}"
    )

    print(
        f"Ratings: {standings_path}"
    )


if __name__ == "__main__":
    main()
