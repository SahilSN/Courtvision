from __future__ import annotations

import argparse
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from team_rating import (
    INITIAL_RATING,
    RATING_RESULTS_DIR,
    binary_metrics,
    expected_home_win_probability,
    load_game_features,
)


# ============================================================
# Frozen Team Courtvision Rating v1 parameters
# ============================================================

FROZEN_K = 30.0
FROZEN_HCA = 35.0

FROZEN_MARGIN_SCALE = 40.0
FROZEN_MARGIN_WEIGHT = 1.0
FROZEN_ALPHA = 1.0


# ============================================================
# Courtvision dominance
# ============================================================

def margin_dominance(
    winner_margin,
    margin_scale,
):
    winner_margin = float(
        winner_margin
    )

    margin_scale = float(
        margin_scale
    )

    if margin_scale <= 0:
        raise ValueError(
            "margin_scale must be positive."
        )

    return float(
        np.tanh(
            winner_margin
            / margin_scale
        )
    )


def wp_control_dominance(
    winner_avg_win_probability,
):
    value = (
        2.0
        * (
            float(
                winner_avg_win_probability
            )
            - 0.5
        )
    )

    return float(
        np.clip(
            value,
            0.0,
            1.0,
        )
    )


def combined_dominance(
    margin_component,
    wp_component,
    margin_weight,
):
    margin_weight = float(
        margin_weight
    )

    if not (
        0.0
        <= margin_weight
        <= 1.0
    ):
        raise ValueError(
            "margin_weight must be between 0 and 1."
        )

    wp_weight = (
        1.0
        - margin_weight
    )

    return float(
        margin_weight
        * float(
            margin_component
        )
        + wp_weight
        * float(
            wp_component
        )
    )


def dominance_multiplier(
    dominance_score,
    alpha,
):
    alpha = float(
        alpha
    )

    if alpha < 0:
        raise ValueError(
            "alpha must be non-negative."
        )

    return float(
        1.0
        + alpha
        * float(
            dominance_score
        )
    )


# ============================================================
# Sequential Courtvision rating
# ============================================================

def run_courtvision_rating(
    games,
    margin_scale,
    margin_weight,
    alpha,
    k_factor=FROZEN_K,
    home_court_advantage=FROZEN_HCA,
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

        d_margin = (
            margin_dominance(
                winner_margin=(
                    game[
                        "winnerMargin"
                    ]
                ),
                margin_scale=(
                    margin_scale
                ),
            )
        )

        d_wp = (
            wp_control_dominance(
                game[
                    "winnerAvgWinProbability"
                ]
            )
        )

        d_combined = (
            combined_dominance(
                margin_component=(
                    d_margin
                ),
                wp_component=(
                    d_wp
                ),
                margin_weight=(
                    margin_weight
                ),
            )
        )

        multiplier = (
            dominance_multiplier(
                dominance_score=(
                    d_combined
                ),
                alpha=(
                    alpha
                ),
            )
        )

        rating_change = float(
            float(
                k_factor
            )
            * multiplier
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

                "winner":
                    game[
                        "winner"
                    ],

                "winnerMargin":
                    float(
                        game[
                            "winnerMargin"
                        ]
                    ),

                "winnerAvgWinProbability":
                    float(
                        game[
                            "winnerAvgWinProbability"
                        ]
                    ),

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

                "marginDominance":
                    d_margin,

                "wpControlDominance":
                    d_wp,

                "dominanceScore":
                    d_combined,

                "dominanceMultiplier":
                    multiplier,

                "homeRatingChange":
                    rating_change,

                "awayRatingChange":
                    -rating_change,

                "homeRatingAfter":
                    home_rating_after,

                "awayRatingAfter":
                    away_rating_after,
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

    teams = sorted(
        ratings.keys()
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

            for team in teams
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

def evaluate_courtvision_history(
    history,
):
    return (
        binary_metrics(
            history[
                "homeWin"
            ],
            history[
                "homeExpectedWinProb"
            ],
        )
    )


# ============================================================
# Validation
# ============================================================

def validate_courtvision_history(
    history,
    standings,
):
    if history.empty:
        raise ValueError(
            "Courtvision rating history is empty."
        )

    if len(
        standings
    ) != 30:
        raise ValueError(
            "Expected 30 teams."
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
            "Courtvision rating is not zero-sum."
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
            "League mean drifted away from 1500."
        )

    if not (
        (
            history[
                "marginDominance"
            ]
            >= 0
        )
        &
        (
            history[
                "marginDominance"
            ]
            <= 1
        )
    ).all():
        raise ValueError(
            "Invalid margin dominance values."
        )

    if not (
        (
            history[
                "wpControlDominance"
            ]
            >= 0
        )
        &
        (
            history[
                "wpControlDominance"
            ]
            <= 1
        )
    ).all():
        raise ValueError(
            "Invalid WP-control dominance values."
        )

    if not (
        (
            history[
                "dominanceScore"
            ]
            >= 0
        )
        &
        (
            history[
                "dominanceScore"
            ]
            <= 1
        )
    ).all():
        raise ValueError(
            "Invalid combined dominance values."
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
            "Rating-change sign does not match the result."
        )

    print(
        "✓ Courtvision Rating validation passed."
    )


# ============================================================
# Development grid
# ============================================================

def tune_courtvision_rating(
    games,
    margin_scales=None,
    margin_weights=None,
    alpha_values=None,
):
    if margin_scales is None:
        margin_scales = [
            8,
            10,
            12,
            15,
            18,
            20,
            25,
        ]

    if margin_weights is None:
        margin_weights = [
            0.00,
            0.25,
            0.50,
            0.75,
            1.00,
        ]

    if alpha_values is None:
        alpha_values = [
            0.00,
            0.10,
            0.25,
            0.50,
            0.75,
            1.00,
        ]

    rows = []

    for margin_scale in (
        margin_scales
    ):
        for margin_weight in (
            margin_weights
        ):
            for alpha in (
                alpha_values
            ):
                history, _ = (
                    run_courtvision_rating(
                        games=games,
                        margin_scale=(
                            margin_scale
                        ),
                        margin_weight=(
                            margin_weight
                        ),
                        alpha=(
                            alpha
                        ),
                    )
                )

                metrics = (
                    evaluate_courtvision_history(
                        history
                    )
                )

                rows.append(
                    {
                        "marginScale":
                            float(
                                margin_scale
                            ),

                        "marginWeight":
                            float(
                                margin_weight
                            ),

                        "wpWeight":
                            float(
                                1.0
                                - margin_weight
                            ),

                        "alpha":
                            float(
                                alpha
                            ),

                        **metrics,
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
# CLI
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Courtvision Team Rating v1 — "
            "Stage 3 dominance-aware rating."
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
        "--margin-scale",
        type=float,
        default=None,
    )

    parser.add_argument(
        "--margin-weight",
        type=float,
        default=None,
    )

    parser.add_argument(
        "--alpha",
        type=float,
        default=None,
    )

    return parser.parse_args()


def main():
    args = parse_args()

    games = load_game_features(
        args.season
    )

    RATING_RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if args.tune:
        print(
            "Courtvision Rating v1 — "
            "Stage 3 Development"
        )

        print(
            f"Season: {args.season}"
        )

        print(
            f"Frozen K: {FROZEN_K:g}"
        )

        print(
            f"Frozen HCA: {FROZEN_HCA:g}"
        )

        print()

        grid = (
            tune_courtvision_rating(
                games
            )
        )

        path = (
            RATING_RESULTS_DIR
            / (
                f"{args.season}_"
                f"courtvision_rating_grid_v1.csv"
            )
        )

        grid.to_csv(
            path,
            index=False,
        )

        print(
            grid.head(
                20
            ).to_string(
                index=False
            )
        )

        print()
        print(
            f"Saved: {path}"
        )

        return

    if (
        args.margin_scale is None
        or args.margin_weight is None
        or args.alpha is None
    ):
        raise ValueError(
            "--margin-scale, --margin-weight, and --alpha "
            "are required unless --tune is used."
        )

    history, standings = (
        run_courtvision_rating(
            games=games,
            margin_scale=(
                args.margin_scale
            ),
            margin_weight=(
                args.margin_weight
            ),
            alpha=(
                args.alpha
            ),
        )
    )

    validate_courtvision_history(
        history,
        standings,
    )

    metrics = (
        evaluate_courtvision_history(
            history
        )
    )

    history_path = (
        RATING_RESULTS_DIR
        / (
            f"{args.season}_"
            f"courtvision_rating_history_v1.csv"
        )
    )

    ratings_path = (
        RATING_RESULTS_DIR
        / (
            f"{args.season}_"
            f"courtvision_rating_ratings_v1.csv"
        )
    )

    history.to_csv(
        history_path,
        index=False,
    )

    standings.to_csv(
        ratings_path,
        index=False,
    )

    print()
    print(
        "Courtvision Rating v1"
    )

    print(
        f"Margin scale: {args.margin_scale:g}"
    )

    print(
        f"Margin weight: {args.margin_weight:g}"
    )

    print(
        f"WP weight: {1.0 - args.margin_weight:g}"
    )

    print(
        f"Alpha: {args.alpha:g}"
    )

    print()

    for key, value in (
        metrics.items()
    ):
        print(
            f"  {key}: {value:.6f}"
        )

    print()

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
        f"Ratings: {ratings_path}"
    )


if __name__ == "__main__":
    main()
