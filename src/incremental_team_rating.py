from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from courtvision_rating import (
    FROZEN_ALPHA,
    FROZEN_HCA,
    FROZEN_K,
    FROZEN_MARGIN_SCALE,
    FROZEN_MARGIN_WEIGHT,
    combined_dominance,
    dominance_multiplier,
    margin_dominance,
    wp_control_dominance,
)

from team_rating import (
    INITIAL_RATING,
    expected_home_win_probability,
)

from team_season_intelligence import (
    build_team_game_history,
)


ROOT_DIR = (
    Path(__file__)
    .resolve()
    .parents[1]
)

DEFAULT_RUNTIME_ROOT = (
    ROOT_DIR
    / "data"
    / "runtime"
    / "team_rating"
)


HISTORY_COLUMNS = [
    "season",
    "gameDate",
    "gameId",
    "homeTeam",
    "awayTeam",
    "homeWin",
    "winner",
    "winnerMargin",
    "winnerAvgWinProbability",
    "homeRatingBefore",
    "awayRatingBefore",
    "homeExpectedWinProb",
    "awayExpectedWinProb",
    "marginDominance",
    "wpControlDominance",
    "dominanceScore",
    "dominanceMultiplier",
    "homeRatingChange",
    "awayRatingChange",
    "homeRatingAfter",
    "awayRatingAfter",
]


REQUIRED_GAME_COLUMNS = [
    "season",
    "gameDate",
    "gameId",
    "homeTeam",
    "awayTeam",
    "homeWin",
    "winner",
    "winnerMargin",
    "winnerAvgWinProbability",
]


def normalize_game_id(
    value,
):
    return str(
        value
    ).zfill(
        10
    )


def empty_team_state():
    return {
        "rating":
            float(
                INITIAL_RATING
            ),

        "wins":
            0,

        "losses":
            0,

        "peakRating":
            float(
                INITIAL_RATING
            ),

        "lowestRating":
            float(
                INITIAL_RATING
            ),
    }


def atomic_write_text(
    path,
    text,
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path = (
        path.parent
        / (
            path.name
            + ".tmp"
        )
    )

    temp_path.write_text(
        text
    )

    os.replace(
        temp_path,
        path,
    )


def atomic_write_csv(
    df,
    path,
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path = (
        path.parent
        / (
            path.name
            + ".tmp"
        )
    )

    df.to_csv(
        temp_path,
        index=False,
    )

    os.replace(
        temp_path,
        path,
    )


def validate_games(
    games,
):
    missing = [
        column
        for column in REQUIRED_GAME_COLUMNS
        if column not in games.columns
    ]

    if missing:
        raise ValueError(
            "Input games are missing required columns: "
            f"{missing}"
        )

    if games[
        "gameId"
    ].isna().any():
        raise ValueError(
            "gameId contains missing values."
        )

    if games[
        "gameDate"
    ].isna().any():
        raise ValueError(
            "gameDate contains missing values."
        )

    home_win = (
        pd.to_numeric(
            games[
                "homeWin"
            ],
            errors="coerce",
        )
    )

    if (
        home_win.isna().any()
        or not home_win.isin(
            [
                0,
                1,
            ]
        ).all()
    ):
        raise ValueError(
            "homeWin must contain only 0/1."
        )

    margins = pd.to_numeric(
        games[
            "winnerMargin"
        ],
        errors="coerce",
    )

    if margins.isna().any():
        raise ValueError(
            "winnerMargin contains invalid values."
        )

    if (
        margins
        <= 0
    ).any():
        raise ValueError(
            "winnerMargin must be positive for completed games."
        )


def canonicalize_games(
    games,
):
    games = games.copy()

    validate_games(
        games
    )

    games[
        "gameId"
    ] = (
        games[
            "gameId"
        ]
        .map(
            normalize_game_id
        )
    )

    games[
        "_sortDate"
    ] = pd.to_datetime(
        games[
            "gameDate"
        ],
        errors="coerce",
    )

    if games[
        "_sortDate"
    ].isna().any():
        raise ValueError(
            "Invalid gameDate detected."
        )

    games = (
        games
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

    if games[
        "gameId"
    ].duplicated().any():
        duplicates = (
            games.loc[
                games[
                    "gameId"
                ].duplicated(
                    keep=False
                ),
                "gameId",
            ]
            .tolist()
        )

        raise ValueError(
            "Duplicate game IDs in input: "
            f"{duplicates[:10]}"
        )

    return games


def load_history(
    history_path,
):
    if not history_path.exists():
        return pd.DataFrame(
            columns=HISTORY_COLUMNS
        )

    history = pd.read_csv(
        history_path,
        dtype={
            "gameId":
                str,
        },
    )

    missing = [
        column
        for column in HISTORY_COLUMNS
        if column not in history.columns
    ]

    if missing:
        raise ValueError(
            "Existing runtime history has an "
            "unexpected schema. Missing: "
            f"{missing}"
        )

    history[
        "gameId"
    ] = (
        history[
            "gameId"
        ]
        .map(
            normalize_game_id
        )
    )

    if history[
        "gameId"
    ].duplicated().any():
        raise ValueError(
            "Existing runtime history contains "
            "duplicate game IDs."
        )

    return history[
        HISTORY_COLUMNS
    ].copy()


def rebuild_state_from_history(
    history,
):
    teams = defaultdict(
        empty_team_state
    )

    processed_game_ids = []

    if history.empty:
        return (
            teams,
            processed_game_ids,
        )

    ordered = history.copy()

    ordered[
        "_sortDate"
    ] = pd.to_datetime(
        ordered[
            "gameDate"
        ],
        errors="coerce",
    )

    ordered = (
        ordered
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
    )

    for _, row in ordered.iterrows():
        home = str(
            row[
                "homeTeam"
            ]
        )

        away = str(
            row[
                "awayTeam"
            ]
        )

        home_win = int(
            row[
                "homeWin"
            ]
        )

        home_after = float(
            row[
                "homeRatingAfter"
            ]
        )

        away_after = float(
            row[
                "awayRatingAfter"
            ]
        )

        home_state = teams[
            home
        ]

        away_state = teams[
            away
        ]

        home_state[
            "rating"
        ] = home_after

        away_state[
            "rating"
        ] = away_after

        if home_win == 1:
            home_state[
                "wins"
            ] += 1

            away_state[
                "losses"
            ] += 1

        else:
            away_state[
                "wins"
            ] += 1

            home_state[
                "losses"
            ] += 1

        home_state[
            "peakRating"
        ] = max(
            float(
                home_state[
                    "peakRating"
                ]
            ),
            home_after,
        )

        home_state[
            "lowestRating"
        ] = min(
            float(
                home_state[
                    "lowestRating"
                ]
            ),
            home_after,
        )

        away_state[
            "peakRating"
        ] = max(
            float(
                away_state[
                    "peakRating"
                ]
            ),
            away_after,
        )

        away_state[
            "lowestRating"
        ] = min(
            float(
                away_state[
                    "lowestRating"
                ]
            ),
            away_after,
        )

        processed_game_ids.append(
            normalize_game_id(
                row[
                    "gameId"
                ]
            )
        )

    return (
        teams,
        processed_game_ids,
    )


def process_game(
    game,
    teams,
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

    home_state = teams[
        home_team
    ]

    away_state = teams[
        away_team
    ]

    home_rating_before = float(
        home_state[
            "rating"
        ]
    )

    away_rating_before = float(
        away_state[
            "rating"
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
                FROZEN_HCA
            ),
        )
    )

    away_expected = (
        1.0
        - home_expected
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
                FROZEN_MARGIN_SCALE
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
                FROZEN_MARGIN_WEIGHT
            ),
        )
    )

    multiplier = (
        dominance_multiplier(
            dominance_score=(
                d_combined
            ),
            alpha=(
                FROZEN_ALPHA
            ),
        )
    )

    home_rating_change = float(
        float(
            FROZEN_K
        )
        * multiplier
        * (
            float(
                home_win
            )
            - float(
                home_expected
            )
        )
    )

    away_rating_change = (
        -home_rating_change
    )

    home_rating_after = (
        home_rating_before
        + home_rating_change
    )

    away_rating_after = (
        away_rating_before
        + away_rating_change
    )

    winner = str(
        game[
            "winner"
        ]
    )

    expected_winner = (
        home_team
        if home_win == 1
        else away_team
    )

    if winner != expected_winner:
        raise ValueError(
            f"Winner mismatch for game "
            f"{game['gameId']}: "
            f"winner={winner}, "
            f"homeWin={home_win}"
        )

    if home_win == 1:
        home_state[
            "wins"
        ] += 1

        away_state[
            "losses"
        ] += 1

    else:
        away_state[
            "wins"
        ] += 1

        home_state[
            "losses"
        ] += 1

    home_state[
        "rating"
    ] = float(
        home_rating_after
    )

    away_state[
        "rating"
    ] = float(
        away_rating_after
    )

    home_state[
        "peakRating"
    ] = max(
        float(
            home_state[
                "peakRating"
            ]
        ),
        float(
            home_rating_after
        ),
    )

    home_state[
        "lowestRating"
    ] = min(
        float(
            home_state[
                "lowestRating"
            ]
        ),
        float(
            home_rating_after
        ),
    )

    away_state[
        "peakRating"
    ] = max(
        float(
            away_state[
                "peakRating"
            ]
        ),
        float(
            away_rating_after
        ),
    )

    away_state[
        "lowestRating"
    ] = min(
        float(
            away_state[
                "lowestRating"
            ]
        ),
        float(
            away_rating_after
        ),
    )

    return {
        "season":
            str(
                game[
                    "season"
                ]
            ),

        "gameDate":
            str(
                game[
                    "gameDate"
                ]
            ),

        "gameId":
            normalize_game_id(
                game[
                    "gameId"
                ]
            ),

        "homeTeam":
            home_team,

        "awayTeam":
            away_team,

        "homeWin":
            home_win,

        "winner":
            winner,

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
            float(
                home_rating_before
            ),

        "awayRatingBefore":
            float(
                away_rating_before
            ),

        "homeExpectedWinProb":
            float(
                home_expected
            ),

        "awayExpectedWinProb":
            float(
                away_expected
            ),

        "marginDominance":
            float(
                d_margin
            ),

        "wpControlDominance":
            float(
                d_wp
            ),

        "dominanceScore":
            float(
                d_combined
            ),

        "dominanceMultiplier":
            float(
                multiplier
            ),

        "homeRatingChange":
            float(
                home_rating_change
            ),

        "awayRatingChange":
            float(
                away_rating_change
            ),

        "homeRatingAfter":
            float(
                home_rating_after
            ),

        "awayRatingAfter":
            float(
                away_rating_after
            ),
    }


def build_ratings_table(
    teams,
):
    rows = []

    for team, state in teams.items():
        rows.append(
            {
                "team":
                    team,

                "wins":
                    int(
                        state[
                            "wins"
                        ]
                    ),

                "losses":
                    int(
                        state[
                            "losses"
                        ]
                    ),

                "currentRating":
                    float(
                        state[
                            "rating"
                        ]
                    ),

                "peakRating":
                    float(
                        state[
                            "peakRating"
                        ]
                    ),

                "lowestRating":
                    float(
                        state[
                            "lowestRating"
                        ]
                    ),
            }
        )

    ratings = pd.DataFrame(
        rows
    )

    if ratings.empty:
        return pd.DataFrame(
            columns=[
                "ratingRank",
                "team",
                "wins",
                "losses",
                "currentRating",
                "peakRating",
                "lowestRating",
            ]
        )

    ratings = (
        ratings
        .sort_values(
            [
                "currentRating",
                "team",
            ],
            ascending=[
                False,
                True,
            ],
            kind="mergesort",
        )
        .reset_index(
            drop=True
        )
    )

    ratings.insert(
        0,
        "ratingRank",
        np.arange(
            1,
            len(
                ratings
            )
            + 1,
        ),
    )

    return ratings


def serialize_state(
    season,
    teams,
    processed_game_ids,
):
    return {
        "version":
            1,

        "season":
            season,

        "parameters":
            {
                "k":
                    float(
                        FROZEN_K
                    ),

                "hca":
                    float(
                        FROZEN_HCA
                    ),

                "marginScale":
                    float(
                        FROZEN_MARGIN_SCALE
                    ),

                "marginWeight":
                    float(
                        FROZEN_MARGIN_WEIGHT
                    ),

                "alpha":
                    float(
                        FROZEN_ALPHA
                    ),
            },

        "processedGameIds":
            list(
                processed_game_ids
            ),

        "teams":
            {
                team:
                    {
                        "rating":
                            float(
                                state[
                                    "rating"
                                ]
                            ),

                        "wins":
                            int(
                                state[
                                    "wins"
                                ]
                            ),

                        "losses":
                            int(
                                state[
                                    "losses"
                                ]
                            ),

                        "peakRating":
                            float(
                                state[
                                    "peakRating"
                                ]
                            ),

                        "lowestRating":
                            float(
                                state[
                                    "lowestRating"
                                ]
                            ),
                    }

                for team, state
                in sorted(
                    teams.items()
                )
            },
    }


def write_outputs(
    season,
    runtime_dir,
    history,
    teams,
):
    history_path = (
        runtime_dir
        / "rating_history_v1.csv"
    )

    ratings_path = (
        runtime_dir
        / "ratings_v1.csv"
    )

    team_games_path = (
        runtime_dir
        / "team_rating_games_v1.csv"
    )

    state_path = (
        runtime_dir
        / "state.json"
    )

    history = history[
        HISTORY_COLUMNS
    ].copy()

    ratings = (
        build_ratings_table(
            teams
        )
    )

    if history.empty:
        team_games = pd.DataFrame()

    else:
        team_games = (
            build_team_game_history(
                history
            )
        )

    processed_game_ids = (
        history[
            "gameId"
        ]
        .map(
            normalize_game_id
        )
        .tolist()
    )

    # History is canonical.
    # Write it first. If a crash occurs before state.json,
    # state is reconstructed from history on the next run.
    atomic_write_csv(
        history,
        history_path,
    )

    atomic_write_csv(
        ratings,
        ratings_path,
    )

    atomic_write_csv(
        team_games,
        team_games_path,
    )

    state = serialize_state(
        season=season,
        teams=teams,
        processed_game_ids=(
            processed_game_ids
        ),
    )

    atomic_write_text(
        state_path,
        json.dumps(
            state,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )

    return {
        "history":
            history_path,

        "ratings":
            ratings_path,

        "teamGames":
            team_games_path,

        "state":
            state_path,
    }


def run_incremental_update(
    season,
    games,
    runtime_root=DEFAULT_RUNTIME_ROOT,
):
    runtime_dir = (
        Path(
            runtime_root
        )
        / season
    )

    runtime_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    history_path = (
        runtime_dir
        / "rating_history_v1.csv"
    )

    history = load_history(
        history_path
    )

    teams, processed_game_ids = (
        rebuild_state_from_history(
            history
        )
    )

    processed = set(
        processed_game_ids
    )

    games = canonicalize_games(
        games
    )

    input_seasons = set(
        games[
            "season"
        ]
        .astype(
            str
        )
        .unique()
        .tolist()
    )

    if input_seasons != {
        str(
            season
        )
    }:
        raise ValueError(
            "Input contains unexpected seasons: "
            f"{sorted(input_seasons)}; "
            f"expected only {season}."
        )

    pending = (
        games.loc[
            ~games[
                "gameId"
            ].isin(
                processed
            )
        ]
        .copy()
    )

    if pending.empty:
        print(
            "No new completed games."
        )

        paths = write_outputs(
            season=season,
            runtime_dir=runtime_dir,
            history=history,
            teams=teams,
        )

        return (
            history,
            build_ratings_table(
                teams
            ),
            paths,
        )

    new_rows = []

    for _, game in pending.iterrows():
        row = process_game(
            game=game,
            teams=teams,
        )

        new_rows.append(
            row
        )

    new_history = pd.DataFrame(
        new_rows,
        columns=HISTORY_COLUMNS,
    )

    if history.empty:
        history = (
            new_history
            .copy()
            .reset_index(
                drop=True
            )
        )

    else:
        history = pd.concat(
            [
                history,
                new_history,
            ],
            ignore_index=True,
        )

    history[
        "_sortDate"
    ] = pd.to_datetime(
        history[
            "gameDate"
        ],
        errors="coerce",
    )

    history = (
        history
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

    if history[
        "gameId"
    ].duplicated().any():
        raise RuntimeError(
            "Incremental update produced "
            "duplicate game IDs."
        )

    paths = write_outputs(
        season=season,
        runtime_dir=runtime_dir,
        history=history,
        teams=teams,
    )

    ratings = build_ratings_table(
        teams
    )

    print(
        f"Processed {len(pending):,} new game(s)."
    )

    print(
        f"Total processed: {len(history):,}"
    )

    return (
        history,
        ratings,
        paths,
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Incrementally update frozen Team "
            "Courtvision Rating v1."
        )
    )

    parser.add_argument(
        "--season",
        required=True,
    )

    parser.add_argument(
        "--games-file",
        required=True,
        help=(
            "CSV containing completed canonical "
            "game rows."
        ),
    )

    parser.add_argument(
        "--runtime-root",
        default=str(
            DEFAULT_RUNTIME_ROOT
        ),
    )

    return parser.parse_args()


def main():
    args = parse_args()

    games = pd.read_csv(
        args.games_file,
        dtype={
            "gameId":
                str,
        },
    )

    history, ratings, paths = (
        run_incremental_update(
            season=args.season,
            games=games,
            runtime_root=(
                Path(
                    args.runtime_root
                )
            ),
        )
    )

    print()
    print(
        "Incremental Team Courtvision Rating v1"
    )

    print(
        f"Season: {args.season}"
    )

    print(
        f"Games processed: {len(history):,}"
    )

    print()

    if not ratings.empty:
        print(
            ratings.head(
                10
            ).to_string(
                index=False
            )
        )

    print()

    for name, path in paths.items():
        print(
            f"{name}: {path}"
        )


if __name__ == "__main__":
    main()
