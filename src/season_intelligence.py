from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from nba_api.stats.static import teams as nba_teams

from player_impact import (
    add_predictions,
    load_model,
    load_season_data,
)


ROOT_DIR = (
    Path(__file__)
    .resolve()
    .parents[1]
)

RESULTS_DIR = (
    ROOT_DIR
    / "results"
    / "season_intelligence"
)


# ============================================================
# Team metadata
# ============================================================

TEAM_ID_TO_TRICODE = {
    int(team["id"]):
        str(team["abbreviation"])

    for team in nba_teams.get_teams()
}


def team_tricode(
    team_id,
):
    try:
        team_id = int(
            team_id
        )

    except (
        TypeError,
        ValueError,
    ):
        return ""

    return (
        TEAM_ID_TO_TRICODE.get(
            team_id,
            str(team_id),
        )
    )


# ============================================================
# Game duration
# ============================================================

def game_duration_seconds(
    game_df,
):
    """
    NBA regulation is 48 minutes.

    Each overtime period adds five minutes.
    """

    if (
        "period"
        not in game_df.columns
        or game_df.empty
    ):
        max_elapsed = float(
            pd.to_numeric(
                game_df[
                    "elapsedGameTime"
                ],
                errors="coerce",
            ).max()
        )

        return max(
            2880.0,
            max_elapsed,
        )

    max_period = int(
        pd.to_numeric(
            game_df[
                "period"
            ],
            errors="coerce",
        )
        .fillna(4)
        .max()
    )

    overtime_periods = max(
        0,
        max_period - 4,
    )

    return float(
        2880
        + 300
        * overtime_periods
    )


# ============================================================
# Time-weighted winner control
# ============================================================

def collapse_probability_states(
    game_df,
):
    """
    Keep the final modeled state at each unique game clock.

    Same-clock play sequences can contain several state rows.
    Courtvision uses the last state at that timestamp as the
    state that persists until the next unique timestamp.
    """

    states = (
        game_df[
            [
                "elapsedGameTime",
                "winProbability",
            ]
        ]
        .copy()
    )

    states[
        "elapsedGameTime"
    ] = pd.to_numeric(
        states[
            "elapsedGameTime"
        ],
        errors="coerce",
    )

    states[
        "winProbability"
    ] = pd.to_numeric(
        states[
            "winProbability"
        ],
        errors="coerce",
    )

    states = (
        states
        .dropna(
            subset=[
                "elapsedGameTime",
                "winProbability",
            ]
        )
        .sort_values(
            "elapsedGameTime",
            kind="mergesort",
        )
        .groupby(
            "elapsedGameTime",
            sort=True,
            as_index=False,
        )
        .tail(1)
        .sort_values(
            "elapsedGameTime",
            kind="mergesort",
        )
        .reset_index(
            drop=True
        )
    )

    return states


def build_time_weighted_control(
    game_df,
    home_win,
):
    """
    Convert Frozen V7's home-team win probabilities into the
    eventual winner's probability and integrate them over game
    time.

    The first observed modeled state is carried backward to
    t=0. Each state then persists until the next unique game
    timestamp. The final state persists until the end of the
    game, including overtime.
    """

    states = (
        collapse_probability_states(
            game_df
        )
    )

    if states.empty:
        raise ValueError(
            "Game contains no valid V7 probability states."
        )

    duration = (
        game_duration_seconds(
            game_df
        )
    )

    elapsed = (
        states[
            "elapsedGameTime"
        ]
        .to_numpy(
            dtype=float
        )
    )

    home_prob = (
        states[
            "winProbability"
        ]
        .to_numpy(
            dtype=float
        )
    )

    home_prob = np.clip(
        home_prob,
        0.0,
        1.0,
    )

    if int(
        home_win
    ) == 1:
        winner_prob = (
            home_prob
        )

    else:
        winner_prob = (
            1.0
            - home_prob
        )

    # --------------------------------------------------------
    # State durations
    #
    # first probability:
    #   t = 0 -> second unique state
    #
    # middle probabilities:
    #   current timestamp -> next timestamp
    #
    # final probability:
    #   final timestamp -> final buzzer
    #
    # This is equivalent to prepending t=0 with the first
    # observed probability.
    # --------------------------------------------------------

    boundaries = np.concatenate(
        (
            np.array(
                [0.0]
            ),
            elapsed[
                1:
            ],
            np.array(
                [duration]
            ),
        )
    )

    weights = np.diff(
        boundaries
    )

    if len(
        weights
    ) != len(
        winner_prob
    ):
        raise RuntimeError(
            "Probability state / time-weight mismatch."
        )

    # Defensive handling for malformed clocks.
    weights = np.clip(
        weights,
        0.0,
        None,
    )

    total_weight = float(
        weights.sum()
    )

    if total_weight <= 0:
        raise ValueError(
            "Game has no positive time duration."
        )

    average_probability = float(
        np.average(
            winner_prob,
            weights=weights,
        )
    )

    time_above_50 = float(
        weights[
            winner_prob
            >= 0.50
        ].sum()
    )

    time_above_75 = float(
        weights[
            winner_prob
            >= 0.75
        ].sum()
    )

    return {
        "gameDurationSeconds":
            float(
                duration
            ),

        "winnerAvgWinProbability":
            average_probability,

        "winnerMinWinProbability":
            float(
                winner_prob.min()
            ),

        "winnerMaxWinProbability":
            float(
                winner_prob.max()
            ),

        "winnerTimeAbove50":
            time_above_50,

        "winnerTimeAbove75":
            time_above_75,

        "winnerShareAbove50":
            float(
                time_above_50
                / total_weight
            ),

        "winnerShareAbove75":
            float(
                time_above_75
                / total_weight
            ),
    }


# ============================================================
# Score / game-shape features
# ============================================================

def final_scores(
    game_df,
):
    home_score = int(
        pd.to_numeric(
            game_df[
                "scoreHome"
            ],
            errors="coerce",
        )
        .fillna(0)
        .max()
    )

    away_score = int(
        pd.to_numeric(
            game_df[
                "scoreAway"
            ],
            errors="coerce",
        )
        .fillna(0)
        .max()
    )

    return (
        home_score,
        away_score,
    )


def largest_winner_deficit(
    game_df,
    home_win,
):
    home_score = (
        pd.to_numeric(
            game_df[
                "scoreHome"
            ],
            errors="coerce",
        )
        .ffill()
        .fillna(0)
    )

    away_score = (
        pd.to_numeric(
            game_df[
                "scoreAway"
            ],
            errors="coerce",
        )
        .ffill()
        .fillna(0)
    )

    home_diff = (
        home_score
        - away_score
    )

    if int(
        home_win
    ) == 1:
        winner_diff = (
            home_diff
        )

    else:
        winner_diff = (
            -home_diff
        )

    min_winner_diff = float(
        winner_diff.min()
    )

    return float(
        max(
            0.0,
            -min_winner_diff,
        )
    )


# ============================================================
# Canonical game row
# ============================================================

def build_game_feature_row(
    game_df,
    season,
):
    if game_df.empty:
        raise ValueError(
            "Cannot build features from an empty game."
        )

    game_df = (
        game_df
        .sort_values(
            "elapsedGameTime",
            kind="mergesort",
        )
        .reset_index(
            drop=True
        )
    )

    game_id = str(
        game_df[
            "gameId"
        ].iloc[0]
    )

    # Training CSVs often deserialize game IDs numerically.
    # Restore the NBA canonical ten-character representation.
    try:
        game_id = (
            str(
                int(
                    float(
                        game_id
                    )
                )
            )
            .zfill(10)
        )

    except (
        TypeError,
        ValueError,
    ):
        pass

    home_team_id = int(
        game_df[
            "homeTeamId"
        ].iloc[0]
    )

    away_team_id = int(
        game_df[
            "awayTeamId"
        ].iloc[0]
    )

    home_team = (
        team_tricode(
            home_team_id
        )
    )

    away_team = (
        team_tricode(
            away_team_id
        )
    )

    home_score, away_score = (
        final_scores(
            game_df
        )
    )

    if home_score == away_score:
        raise ValueError(
            f"Game {game_id} ended with a tied final score."
        )

    home_win = int(
        home_score
        > away_score
    )

    winner = (
        home_team
        if home_win
        else away_team
    )

    final_margin = int(
        home_score
        - away_score
    )

    winner_margin = int(
        abs(
            final_margin
        )
    )

    game_date = ""

    if (
        "gameDate"
        in game_df.columns
    ):
        game_date = str(
            game_df[
                "gameDate"
            ].iloc[0]
        )

    control = (
        build_time_weighted_control(
            game_df,
            home_win,
        )
    )

    return {
        "gameId":
            game_id,

        "gameDate":
            game_date,

        "season":
            str(
                season
            ),

        "homeTeam":
            home_team,

        "awayTeam":
            away_team,

        "homeTeamId":
            home_team_id,

        "awayTeamId":
            away_team_id,

        "homeScore":
            home_score,

        "awayScore":
            away_score,

        "winner":
            winner,

        "homeWin":
            home_win,

        # Home-relative margin.
        "finalMargin":
            final_margin,

        # Always positive.
        "winnerMargin":
            winner_margin,

        **control,

        "largestWinnerDeficit":
            largest_winner_deficit(
                game_df,
                home_win,
            ),
    }


# ============================================================
# Season builder
# ============================================================

def build_season_intelligence_dataset(
    season,
):
    """
    Build Stage 1 of Team Courtvision Rating v1:

    one deterministic, auditable row per game containing final
    result, margin, and time-weighted Frozen V7 control.
    """

    print(
        f"Loading {season} season data..."
    )

    season_df = (
        load_season_data(
            season
        )
        .copy()
    )

    print(
        "Loading Frozen V7..."
    )

    model, scaler, device = (
        load_model()
    )

    print(
        "Running Frozen V7 over season states..."
    )

    season_df = (
        add_predictions(
            season_df,
            model,
            scaler,
            device,
        )
    )

    rows = []

    grouped = (
        season_df.groupby(
            "gameId",
            sort=False,
        )
    )

    total_games = (
        grouped.ngroups
    )

    print(
        f"Building canonical rows for "
        f"{total_games:,} games..."
    )

    for index, (
        _game_id,
        game_df,
    ) in enumerate(
        grouped,
        start=1,
    ):
        rows.append(
            build_game_feature_row(
                game_df,
                season,
            )
        )

        if (
            index % 100 == 0
            or index == total_games
        ):
            print(
                f"  {index:,} / "
                f"{total_games:,}"
            )

    result = pd.DataFrame(
        rows
    )

    if not result.empty:
        result[
            "_sortDate"
        ] = pd.to_datetime(
            result[
                "gameDate"
            ],
            errors="coerce",
        )

        result = (
            result
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

    validate_season_intelligence_dataset(
        result,
        expected_games=(
            total_games
        ),
    )

    return result


# ============================================================
# Validation
# ============================================================

def validate_season_intelligence_dataset(
    df,
    expected_games=None,
):
    required = {
        "gameId",
        "gameDate",
        "season",
        "homeTeam",
        "awayTeam",
        "homeScore",
        "awayScore",
        "winner",
        "homeWin",
        "finalMargin",
        "winnerMargin",
        "gameDurationSeconds",
        "winnerAvgWinProbability",
        "winnerMinWinProbability",
        "winnerMaxWinProbability",
        "winnerTimeAbove50",
        "winnerTimeAbove75",
        "winnerShareAbove50",
        "winnerShareAbove75",
        "largestWinnerDeficit",
    }

    missing = (
        required
        - set(
            df.columns
        )
    )

    if missing:
        raise ValueError(
            "Season Intelligence dataset is missing "
            f"required columns: {sorted(missing)}"
        )

    if (
        expected_games is not None
        and len(df)
        != int(
            expected_games
        )
    ):
        raise ValueError(
            "Game-count mismatch: "
            f"expected {expected_games}, "
            f"found {len(df)}."
        )

    if df[
        "gameId"
    ].duplicated().any():
        duplicates = (
            df.loc[
                df[
                    "gameId"
                ].duplicated(
                    keep=False
                ),
                "gameId",
            ]
            .tolist()
        )

        raise ValueError(
            "Duplicate game IDs found: "
            f"{duplicates[:10]}"
        )

    probability_columns = [
        "winnerAvgWinProbability",
        "winnerMinWinProbability",
        "winnerMaxWinProbability",
        "winnerShareAbove50",
        "winnerShareAbove75",
    ]

    for column in (
        probability_columns
    ):
        values = pd.to_numeric(
            df[
                column
            ],
            errors="coerce",
        )

        if (
            values.isna().any()
            or (
                values
                < -1e-9
            ).any()
            or (
                values
                > 1.0
                + 1e-9
            ).any()
        ):
            raise ValueError(
                f"Invalid probability values in {column}."
            )

    if not (
        (
            df[
                "winnerMinWinProbability"
            ]
            <= df[
                "winnerAvgWinProbability"
            ]
        )
        &
        (
            df[
                "winnerAvgWinProbability"
            ]
            <= df[
                "winnerMaxWinProbability"
            ]
        )
    ).all():
        raise ValueError(
            "Winner probability min/average/max ordering "
            "is invalid."
        )

    if (
        df[
            "winnerMargin"
        ]
        <= 0
    ).any():
        raise ValueError(
            "Every completed NBA game must have a positive "
            "winner margin."
        )

    if (
        df[
            "winnerTimeAbove50"
        ]
        > (
            df[
                "gameDurationSeconds"
            ]
            + 1e-6
        )
    ).any():
        raise ValueError(
            "winnerTimeAbove50 exceeds game duration."
        )

    if (
        df[
            "winnerTimeAbove75"
        ]
        > (
            df[
                "gameDurationSeconds"
            ]
            + 1e-6
        )
    ).any():
        raise ValueError(
            "winnerTimeAbove75 exceeds game duration."
        )

    # A team cannot spend more time above 75% than above 50%.
    if (
        df[
            "winnerTimeAbove75"
        ]
        > (
            df[
                "winnerTimeAbove50"
            ]
            + 1e-6
        )
    ).any():
        raise ValueError(
            "winnerTimeAbove75 exceeds winnerTimeAbove50."
        )

    if (
        df[
            "winnerShareAbove75"
        ]
        > (
            df[
                "winnerShareAbove50"
            ]
            + 1e-9
        )
    ).any():
        raise ValueError(
            "winnerShareAbove75 exceeds winnerShareAbove50."
        )

    # Home-relative final margin must agree with the winner.
    invalid_home_result = (
        (
            df[
                "homeWin"
            ]
            == 1
        )
        & (
            df[
                "finalMargin"
            ]
            <= 0
        )
    )

    invalid_away_result = (
        (
            df[
                "homeWin"
            ]
            == 0
        )
        & (
            df[
                "finalMargin"
            ]
            >= 0
        )
    )

    if (
        invalid_home_result.any()
        or invalid_away_result.any()
    ):
        raise ValueError(
            "homeWin and finalMargin disagree."
        )

    # winnerMargin must exactly equal the absolute
    # home-relative final margin.
    if not np.allclose(
        df[
            "winnerMargin"
        ].to_numpy(
            dtype=float
        ),
        np.abs(
            df[
                "finalMargin"
            ].to_numpy(
                dtype=float
            )
        ),
        atol=1e-9,
        rtol=0.0,
    ):
        raise ValueError(
            "winnerMargin does not equal abs(finalMargin)."
        )

    # NBA game length should always be regulation plus
    # zero or more five-minute overtime periods.
    durations = (
        df[
            "gameDurationSeconds"
        ]
        .to_numpy(
            dtype=float
        )
    )

    if (
        (
            durations
            < 2880.0
        ).any()
        or (
            np.mod(
                durations
                - 2880.0,
                300.0,
            )
            != 0.0
        ).any()
    ):
        raise ValueError(
            "Invalid NBA game duration detected."
        )

    print(
        "✓ Season Intelligence validation passed."
    )


# ============================================================
# CLI
# ============================================================

def parse_args():
    parser = (
        argparse.ArgumentParser(
            description=(
                "Build the canonical Stage 1 "
                "Courtvision Season Intelligence dataset."
            )
        )
    )

    parser.add_argument(
        "--season",
        required=True,
    )

    parser.add_argument(
        "--output",
        default=None,
    )

    return (
        parser.parse_args()
    )


def main():
    args = (
        parse_args()
    )

    result = (
        build_season_intelligence_dataset(
            args.season
        )
    )

    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if args.output:
        output_path = Path(
            args.output
        )

    else:
        output_path = (
            RESULTS_DIR
            / (
                f"{args.season}_"
                f"game_features_v1.csv"
            )
        )

    result.to_csv(
        output_path,
        index=False,
    )

    print()
    print(
        "Courtvision Season Intelligence — Stage 1"
    )

    print(
        f"Season: {args.season}"
    )

    print(
        f"Games: {len(result):,}"
    )

    print(
        f"Output: {output_path}"
    )

    print()

    preview_columns = [
        "gameDate",
        "gameId",
        "awayTeam",
        "homeTeam",
        "awayScore",
        "homeScore",
        "winner",
        "winnerMargin",
        "winnerAvgWinProbability",
        "largestWinnerDeficit",
    ]

    print(
        result[
            preview_columns
        ]
        .head(10)
        .to_string(
            index=False
        )
    )


if __name__ == "__main__":
    main()
