import argparse
import contextlib
import io
from pathlib import Path

import numpy as np
import pandas as pd

from live_analysis import analyze_live_game
from momentum import (
    MAX_DURATION_SECONDS,
    MAX_OVERLAP_FRACTION,
    MAX_TRANSITIONS,
    MIN_DURATION_SECONDS,
    MIN_SCORE_MARGIN_SWING,
    MIN_TRANSITIONS,
    MIN_WP_SWING,
    STRONG_WP_SWING,
    detect_momentum_runs,
)
from team_metadata import get_team_metadata


ROOT_DIR = (
    Path(__file__)
    .resolve()
    .parents[1]
)

TRAINING_DIR = (
    ROOT_DIR
    / "data"
    / "training"
)

RESULTS_DIR = (
    ROOT_DIR
    / "results"
)


# ============================================================
# Review-only thresholds
# ============================================================

# These do NOT cause structural failure.
# They simply identify runs worth inspecting manually.

REVIEW_LARGE_SWING = 0.40

REVIEW_LONG_RUN_SECONDS = 210

REVIEW_HIGH_TRANSITIONS = 16


# ============================================================
# Game selection
# ============================================================

def normalize_game_id(
    game_id,
):
    value = str(
        int(
            float(
                game_id
            )
        )
    )

    return value.zfill(
        10
    )


def load_game_catalog(
    season,
):
    path = (
        TRAINING_DIR
        / (
            f"{season}"
            "_training_v4_base.csv"
        )
    )

    if not path.exists():
        raise FileNotFoundError(
            f"Missing season dataset: {path}"
        )

    df = pd.read_csv(
        path,
        usecols=[
            "gameId",
            "gameDate",
        ],
    )

    games = (
        df[
            [
                "gameId",
                "gameDate",
            ]
        ]
        .drop_duplicates(
            subset=[
                "gameId",
            ]
        )
        .copy()
    )

    games[
        "gameDate"
    ] = pd.to_datetime(
        games[
            "gameDate"
        ]
    )

    games = (
        games
        .sort_values(
            [
                "gameDate",
                "gameId",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    games[
        "gameId"
    ] = (
        games[
            "gameId"
        ]
        .apply(
            normalize_game_id
        )
    )

    return games


def select_evenly_spaced_games(
    games,
    sample_size,
):
    if sample_size >= len(
        games
    ):
        return games.copy()

    indices = np.linspace(
        0,
        len(games) - 1,
        sample_size,
        dtype=int,
    )

    return (
        games
        .iloc[
            indices
        ]
        .reset_index(
            drop=True
        )
    )


# ============================================================
# Overlap validation
# ============================================================

def interval_overlap_fraction(
    first,
    second,
):
    first_start = float(
        first[
            "startElapsed"
        ]
    )

    first_end = float(
        first[
            "endElapsed"
        ]
    )

    second_start = float(
        second[
            "startElapsed"
        ]
    )

    second_end = float(
        second[
            "endElapsed"
        ]
    )

    overlap = max(
        0.0,
        min(
            first_end,
            second_end,
        )
        - max(
            first_start,
            second_start,
        ),
    )

    first_duration = max(
        1.0,
        first_end
        - first_start,
    )

    second_duration = max(
        1.0,
        second_end
        - second_start,
    )

    return (
        overlap
        / min(
            first_duration,
            second_duration,
        )
    )


def maximum_same_team_overlap(
    runs,
):
    maximum = 0.0

    for first_index in range(
        len(runs)
    ):
        for second_index in range(
            first_index + 1,
            len(runs),
        ):
            first = (
                runs[
                    first_index
                ]
            )

            second = (
                runs[
                    second_index
                ]
            )

            if (
                first[
                    "beneficiaryTeam"
                ]
                != second[
                    "beneficiaryTeam"
                ]
            ):
                continue

            overlap = (
                interval_overlap_fraction(
                    first,
                    second,
                )
            )

            maximum = max(
                maximum,
                overlap,
            )

    return maximum


# ============================================================
# Run-level checks
# ============================================================

def validate_run(
    game_id,
    run_index,
    run,
):
    swing = float(
        run[
            "winProbabilitySwing"
        ]
    )

    before = float(
        run[
            "winProbabilityBefore"
        ]
    )

    after = float(
        run[
            "winProbabilityAfter"
        ]
    )

    duration = float(
        run[
            "durationSeconds"
        ]
    )

    transitions = int(
        run[
            "transitions"
        ]
    )

    beneficiary_points = int(
        run[
            "beneficiaryPoints"
        ]
    )

    opponent_points = int(
        run[
            "opponentPoints"
        ]
    )

    margin_swing = int(
        run[
            "scoreMarginSwing"
        ]
    )

    expected_margin = (
        beneficiary_points
        - opponent_points
    )

    positive_swing = (
        swing > 0
    )

    probability_identity = (
        abs(
            (
                after
                - before
            )
            - swing
        )
        <= 1e-9
    )

    probability_bounds = (
        0.0
        <= before
        <= 1.0
        and 0.0
        <= after
        <= 1.0
    )

    duration_valid = (
        MIN_DURATION_SECONDS
        <= duration
        <= MAX_DURATION_SECONDS
    )

    transitions_valid = (
        MIN_TRANSITIONS
        <= transitions
        <= MAX_TRANSITIONS
    )

    threshold_valid = (
        swing
        >= MIN_WP_SWING
    )

    scoring_identity = (
        margin_swing
        == expected_margin
    )

    qualification_valid = (
        margin_swing
        >= MIN_SCORE_MARGIN_SWING
        or swing
        >= STRONG_WP_SWING
    )

    structural_pass = all(
        [
            positive_swing,
            probability_identity,
            probability_bounds,
            duration_valid,
            transitions_valid,
            threshold_valid,
            scoring_identity,
            qualification_valid,
        ]
    )

    review_large_swing = (
        swing
        >= REVIEW_LARGE_SWING
    )

    review_long_run = (
        duration
        >= REVIEW_LONG_RUN_SECONDS
    )

    review_many_transitions = (
        transitions
        >= REVIEW_HIGH_TRANSITIONS
    )

    review_no_margin_gain = (
        margin_swing
        < MIN_SCORE_MARGIN_SWING
    )

    review_flag = any(
        [
            review_large_swing,
            review_long_run,
            review_many_transitions,
            review_no_margin_gain,
        ]
    )

    return {
        "gameId":
            game_id,

        "runIndex":
            run_index,

        "beneficiaryTeam":
            run[
                "beneficiaryTeam"
            ],

        "opponentTeam":
            run[
                "opponentTeam"
            ],

        "startPeriod":
            run[
                "startPeriod"
            ],

        "startClock":
            run[
                "startClock"
            ],

        "endPeriod":
            run[
                "endPeriod"
            ],

        "endClock":
            run[
                "endClock"
            ],

        "durationSeconds":
            duration,

        "transitions":
            transitions,

        "winProbabilityBefore":
            before,

        "winProbabilityAfter":
            after,

        "winProbabilitySwing":
            swing,

        "winProbabilitySwingPoints":
            (
                swing
                * 100.0
            ),

        "beneficiaryPoints":
            beneficiary_points,

        "opponentPoints":
            opponent_points,

        "scoreMarginSwing":
            margin_swing,

        "structuralPass":
            structural_pass,

        "positiveSwingPass":
            positive_swing,

        "probabilityIdentityPass":
            probability_identity,

        "probabilityBoundsPass":
            probability_bounds,

        "durationPass":
            duration_valid,

        "transitionsPass":
            transitions_valid,

        "thresholdPass":
            threshold_valid,

        "scoringIdentityPass":
            scoring_identity,

        "qualificationPass":
            qualification_valid,

        "reviewFlag":
            review_flag,

        "reviewLargeSwing":
            review_large_swing,

        "reviewLongRun":
            review_long_run,

        "reviewManyTransitions":
            review_many_transitions,

        "reviewNoMarginGain":
            review_no_margin_gain,
    }


# ============================================================
# Game validation
# ============================================================

def validate_game(
    game_id,
    game_date,
    season,
):
    # Suppress analysis-module status output
    # while performing batch validation.
    output = io.StringIO()

    with contextlib.redirect_stdout(
        output
    ):
        result = (
            analyze_live_game(
                game_id=game_id,
                season=season,
                game_date=game_date,
                top_k=3,
                assume_final=True,
            )
        )

    timeline = (
        result[
            "timeline"
        ]
    )

    home_metadata = (
        get_team_metadata(
            result[
                "home_team_id"
            ]
        )
    )

    away_metadata = (
        get_team_metadata(
            result[
                "away_team_id"
            ]
        )
    )

    home_team = (
        home_metadata[
            "tricode"
        ]
    )

    away_team = (
        away_metadata[
            "tricode"
        ]
    )

    momentum = (
        detect_momentum_runs(
            timeline,
            home_team=home_team,
            away_team=away_team,
            top_k=3,
        )
    )

    runs = (
        momentum[
            "all_runs"
        ]
    )

    run_rows = []

    for run_index, run in enumerate(
        runs,
        start=1,
    ):
        run_rows.append(
            validate_run(
                game_id,
                run_index,
                run,
            )
        )

    overlap = (
        maximum_same_team_overlap(
            runs
        )
    )

    overlap_pass = (
        overlap
        <= (
            MAX_OVERLAP_FRACTION
            + 1e-9
        )
    )

    duplicate_windows = (
        len(
            {
                (
                    run[
                        "beneficiaryTeam"
                    ],
                    float(
                        run[
                            "startElapsed"
                        ]
                    ),
                    float(
                        run[
                            "endElapsed"
                        ]
                    ),
                )
                for run in runs
            }
        )
        != len(
            runs
        )
    )

    duplicate_pass = (
        not duplicate_windows
    )

    run_structural_pass = all(
        row[
            "structuralPass"
        ]
        for row in run_rows
    )

    overall_pass = all(
        [
            run_structural_pass,
            overlap_pass,
            duplicate_pass,
        ]
    )

    game_row = {
        "gameId":
            game_id,

        "gameDate":
            game_date,

        "homeTeam":
            home_team,

        "awayTeam":
            away_team,

        "candidateCount":
            momentum[
                "candidate_count"
            ],

        "detectedRuns":
            len(
                runs
            ),

        "homeRuns":
            len(
                momentum[
                    "home_runs"
                ]
            ),

        "awayRuns":
            len(
                momentum[
                    "away_runs"
                ]
            ),

        "maxSameTeamOverlap":
            overlap,

        "overlapPass":
            overlap_pass,

        "duplicateWindowPass":
            duplicate_pass,

        "runStructuralPass":
            run_structural_pass,

        "reviewRuns":
            sum(
                row[
                    "reviewFlag"
                ]
                for row in run_rows
            ),

        "overallPass":
            overall_pass,
    }

    return (
        game_row,
        run_rows,
    )


# ============================================================
# Main
# ============================================================

def parse_args():
    parser = (
        argparse.ArgumentParser(
            description=(
                "Validate Courtvision multi-play "
                "momentum detection across games."
            )
        )
    )

    parser.add_argument(
        "--season",
        default="2024-25",
    )

    parser.add_argument(
        "--sample-size",
        type=int,
        default=10,
    )

    return (
        parser.parse_args()
    )


def main():
    args = (
        parse_args()
    )

    season = (
        args.season
    )

    sample_size = (
        args.sample_size
    )

    games = (
        load_game_catalog(
            season
        )
    )

    sample = (
        select_evenly_spaced_games(
            games,
            sample_size,
        )
    )

    print(
        "Courtvision Momentum Validation"
    )

    print(
        "Season:",
        season,
    )

    print(
        "Available games:",
        len(games),
    )

    print(
        "Validation sample:",
        len(sample),
    )

    print()

    game_rows = []
    run_rows = []
    failures = []

    for index, row in (
        sample.iterrows()
    ):
        game_id = (
            row[
                "gameId"
            ]
        )

        game_date = (
            row[
                "gameDate"
            ]
        )

        print(
            f"[{index + 1}/"
            f"{len(sample)}] "
            f"{game_id} "
            f"{game_date.date()}",
            end=" ... ",
            flush=True,
        )

        try:
            (
                game_result,
                game_runs,
            ) = (
                validate_game(
                    game_id,
                    game_date,
                    season,
                )
            )

            game_rows.append(
                game_result
            )

            run_rows.extend(
                game_runs
            )

            if game_result[
                "overallPass"
            ]:
                print(
                    "PASS"
                )

            else:
                print(
                    "FAIL"
                )

        except Exception as error:
            print(
                "ERROR"
            )

            failures.append(
                {
                    "gameId":
                        game_id,

                    "gameDate":
                        game_date,

                    "error":
                        str(
                            error
                        ),
                }
            )

    games_df = pd.DataFrame(
        game_rows
    )

    runs_df = pd.DataFrame(
        run_rows
    )

    failures_df = pd.DataFrame(
        failures
    )

    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    games_path = (
        RESULTS_DIR
        / (
            f"momentum_{season}"
            "_validation_games.csv"
        )
    )

    runs_path = (
        RESULTS_DIR
        / (
            f"momentum_{season}"
            "_validation_runs.csv"
        )
    )

    failures_path = (
        RESULTS_DIR
        / (
            f"momentum_{season}"
            "_validation_failures.csv"
        )
    )

    games_df.to_csv(
        games_path,
        index=False,
    )

    runs_df.to_csv(
        runs_path,
        index=False,
    )

    failures_df.to_csv(
        failures_path,
        index=False,
    )

    print()
    print(
        "=" * 72
    )

    print(
        "Validation Summary"
    )

    print(
        "=" * 72
    )

    print(
        "Attempted:",
        len(sample),
    )

    print(
        "Successful:",
        len(
            games_df
        ),
    )

    print(
        "Failures:",
        len(
            failures_df
        ),
    )

    if not games_df.empty:
        passed = int(
            games_df[
                "overallPass"
            ].sum()
        )

        print(
            "Structural PASS:",
            passed,
        )

        print(
            "Structural FAIL:",
            (
                len(
                    games_df
                )
                - passed
            ),
        )

        print()

        print(
            "Detected runs per game"
        )

        print(
            "  mean:",
            (
                f"{games_df['detectedRuns'].mean():.2f}"
            ),
        )

        print(
            "  min :",
            int(
                games_df[
                    "detectedRuns"
                ].min()
            ),
        )

        print(
            "  max :",
            int(
                games_df[
                    "detectedRuns"
                ].max()
            ),
        )

        print()

        print(
            "Candidate windows per game"
        )

        print(
            "  mean:",
            (
                f"{games_df['candidateCount'].mean():.1f}"
            ),
        )

        print()

        print(
            "Maximum selected same-team overlap"
        )

        print(
            "  max:",
            (
                f"{games_df['maxSameTeamOverlap'].max() * 100:.1f}%"
            ),
        )

    if not runs_df.empty:
        print()

        print(
            "Selected-run diagnostics"
        )

        print(
            "  runs:",
            len(
                runs_df
            ),
        )

        print(
            "  mean WP swing:",
            (
                f"{runs_df['winProbabilitySwingPoints'].mean():.2f} pp"
            ),
        )

        print(
            "  median WP swing:",
            (
                f"{runs_df['winProbabilitySwingPoints'].median():.2f} pp"
            ),
        )

        print(
            "  max WP swing:",
            (
                f"{runs_df['winProbabilitySwingPoints'].max():.2f} pp"
            ),
        )

        print(
            "  mean duration:",
            (
                f"{runs_df['durationSeconds'].mean():.1f} s"
            ),
        )

        print(
            "  mean score-margin swing:",
            (
                f"{runs_df['scoreMarginSwing'].mean():.2f}"
            ),
        )

        print()

        review_count = int(
            runs_df[
                "reviewFlag"
            ].sum()
        )

        print(
            "Manual-review flags:",
            review_count,
        )

        if review_count:
            print()

            review_columns = [
                "gameId",
                "beneficiaryTeam",
                "startPeriod",
                "startClock",
                "endPeriod",
                "endClock",
                "winProbabilitySwingPoints",
                "beneficiaryPoints",
                "opponentPoints",
                "scoreMarginSwing",
                "durationSeconds",
                "transitions",
                "reviewLargeSwing",
                "reviewLongRun",
                "reviewManyTransitions",
                "reviewNoMarginGain",
            ]

            print(
                runs_df[
                    runs_df[
                        "reviewFlag"
                    ]
                ][
                    review_columns
                ]
                .sort_values(
                    "winProbabilitySwingPoints",
                    ascending=False,
                )
                .to_string(
                    index=False
                )
            )

        print()
        print(
            "Largest 10 detected runs"
        )

        display_columns = [
            "gameId",
            "beneficiaryTeam",
            "startPeriod",
            "startClock",
            "endPeriod",
            "endClock",
            "winProbabilitySwingPoints",
            "beneficiaryPoints",
            "opponentPoints",
            "scoreMarginSwing",
            "durationSeconds",
            "transitions",
        ]

        print(
            runs_df.nlargest(
                min(
                    10,
                    len(
                        runs_df
                    ),
                ),
                "winProbabilitySwingPoints",
            )[
                display_columns
            ]
            .to_string(
                index=False
            )
        )

    print()
    print(
        "Saved:"
    )

    print(
        " ",
        games_path,
    )

    print(
        " ",
        runs_path,
    )

    print(
        " ",
        failures_path,
    )


if __name__ == "__main__":
    main()
