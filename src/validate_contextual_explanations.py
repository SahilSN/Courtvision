from __future__ import annotations

import argparse
import contextlib
import io
from pathlib import Path

import numpy as np
import pandas as pd

from contextual_explanations import (
    build_contextual_explanations,
)
from live_analysis import analyze_live_game
from momentum import detect_momentum_runs
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
# Helpers
# ============================================================

def normalize_game_id(
    game_id,
):
    value = str(
        int(
            float(game_id)
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
        / f"{season}_training_v4_base.csv"
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
        return (
            games.copy()
        )

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


def safe_float(
    value,
    default=0.0,
):
    try:
        if pd.isna(value):
            return default

        return float(value)

    except (
        TypeError,
        ValueError,
    ):
        return default


def safe_int(
    value,
    default=0,
):
    try:
        if pd.isna(value):
            return default

        return int(
            round(
                float(value)
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        return default


# ============================================================
# Explanation checks
# ============================================================

def expected_margin_description_type(
    before_margin,
    after_margin,
):
    if (
        before_margin < 0
        and after_margin > 0
    ):
        return "lead_flip"

    if (
        before_margin < 0
        and after_margin == 0
    ):
        return "tie_created"

    if (
        before_margin == 0
        and after_margin > 0
    ):
        return "tie_broken"

    if (
        before_margin > 0
        and after_margin > before_margin
    ):
        return "lead_extended"

    if (
        before_margin < 0
        and after_margin < 0
        and after_margin > before_margin
    ):
        return "deficit_cut"

    return "other"


def explanation_text_matches_margin(
    explanation,
    margin_type,
):
    text = (
        explanation[
            "summary"
        ]
        .lower()
    )

    if margin_type == "lead_flip":
        return (
            "deficit"
            in text
            and "lead"
            in text
        )

    if margin_type == "tie_created":
        return (
            "tie"
            in text
        )

    if margin_type == "tie_broken":
        return (
            "breaking a tie"
            in text
        )

    if margin_type == "lead_extended":
        return (
            "extending the lead"
            in text
        )

    if margin_type == "deficit_cut":
        return (
            "cutting the deficit"
            in text
        )

    return True


def explanation_headline_matches_margin(
    explanation,
    margin_type,
):
    headline = (
        explanation[
            "headline"
        ]
        .lower()
    )

    if margin_type == "lead_flip":
        return (
            "flipped the game"
            in headline
        )

    if margin_type == "tie_broken":
        return (
            "broke the tie"
            in headline
        )

    if margin_type == "lead_extended":
        return (
            "pulled away"
            in headline
        )

    if margin_type == "deficit_cut":
        return (
            "surged back"
            in headline
        )

    return True


def validate_explanation(
    game_id,
    rank,
    explanation,
    source_run,
    home_team,
):
    beneficiary = (
        explanation[
            "team"
        ]
    )

    beneficiary_is_home = (
        beneficiary
        == home_team
    )

    home_before = safe_int(
        source_run[
            "homeScoreBefore"
        ]
    )

    away_before = safe_int(
        source_run[
            "awayScoreBefore"
        ]
    )

    home_after = safe_int(
        source_run[
            "homeScoreAfter"
        ]
    )

    away_after = safe_int(
        source_run[
            "awayScoreAfter"
        ]
    )

    if beneficiary_is_home:
        before_margin = (
            home_before
            - away_before
        )

        after_margin = (
            home_after
            - away_after
        )

    else:
        before_margin = (
            away_before
            - home_before
        )

        after_margin = (
            away_after
            - home_after
        )

    expected_margin_type = (
        expected_margin_description_type(
            before_margin,
            after_margin,
        )
    )

    score_identity = (
        safe_int(
            source_run[
                "scoreMarginSwing"
            ]
        )
        ==
        (
            safe_int(
                source_run[
                    "beneficiaryPoints"
                ]
            )
            -
            safe_int(
                source_run[
                    "opponentPoints"
                ]
            )
        )
    )

    team_match = (
        explanation[
            "team"
        ]
        ==
        source_run[
            "beneficiaryTeam"
        ]
    )

    opponent_match = (
        explanation[
            "opponent"
        ]
        ==
        source_run[
            "opponentTeam"
        ]
    )

    swing_match = (
        abs(
            safe_float(
                explanation[
                    "winProbabilitySwingPoints"
                ]
            )
            -
            safe_float(
                source_run[
                    "winProbabilitySwingPoints"
                ]
            )
        )
        <= 1e-8
    )

    summary_margin_match = (
        explanation_text_matches_margin(
            explanation,
            expected_margin_type,
        )
    )

    headline_match = (
        explanation_headline_matches_margin(
            explanation,
            expected_margin_type,
        )
    )

    headline_present = bool(
        str(
            explanation[
                "headline"
            ]
        ).strip()
    )

    summary_present = bool(
        str(
            explanation[
                "summary"
            ]
        ).strip()
    )

    context_score_valid = (
        safe_float(
            explanation[
                "contextScore"
            ],
            default=-1,
        )
        >= 0
    )

    structural_pass = all(
        [
            score_identity,
            team_match,
            opponent_match,
            swing_match,
            summary_margin_match,
            headline_match,
            headline_present,
            summary_present,
            context_score_valid,
        ]
    )

    details = (
        explanation.get(
            "details",
            [],
        )
    )

    return {
        "gameId":
            game_id,

        "rank":
            rank,

        "team":
            explanation[
                "team"
            ],

        "opponent":
            explanation[
                "opponent"
            ],

        "headline":
            explanation[
                "headline"
            ],

        "winProbabilitySwingPoints":
            explanation[
                "winProbabilitySwingPoints"
            ],

        "contextScore":
            explanation[
                "contextScore"
            ],

        "beforeMargin":
            before_margin,

        "afterMargin":
            after_margin,

        "marginType":
            expected_margin_type,

        "detailCount":
            len(
                details
            ),

        "hasPlayerContext":
            len(
                details
            )
            > 0,

        "scoreIdentityPass":
            score_identity,

        "teamMatchPass":
            team_match,

        "opponentMatchPass":
            opponent_match,

        "swingMatchPass":
            swing_match,

        "summaryMarginPass":
            summary_margin_match,

        "headlinePass":
            headline_match,

        "structuralPass":
            structural_pass,
    }


# ============================================================
# Run matching
# ============================================================

def find_source_run(
    explanation,
    runs,
):
    for run in runs:
        if (
            run[
                "beneficiaryTeam"
            ]
            != explanation[
                "team"
            ]
        ):
            continue

        if (
            abs(
                safe_float(
                    run[
                        "winProbabilitySwingPoints"
                    ]
                )
                -
                safe_float(
                    explanation[
                        "winProbabilitySwingPoints"
                    ]
                )
            )
            > 1e-8
        ):
            continue

        if (
            safe_int(
                run[
                    "startPeriod"
                ]
            )
            !=
            safe_int(
                explanation[
                    "startPeriod"
                ]
            )
        ):
            continue

        if (
            str(
                run[
                    "startClock"
                ]
            )
            !=
            str(
                explanation[
                    "startClock"
                ]
            )
        ):
            continue

        if (
            safe_int(
                run[
                    "endPeriod"
                ]
            )
            !=
            safe_int(
                explanation[
                    "endPeriod"
                ]
            )
        ):
            continue

        if (
            str(
                run[
                    "endClock"
                ]
            )
            !=
            str(
                explanation[
                    "endClock"
                ]
            )
        ):
            continue

        return run

    return None



def load_cached_player_summary(
    game_id,
):
    """
    Use an existing validated WPA v3 summary when available.

    Contextual-explanation validation should not recompute
    the expensive player-attribution pipeline for every game.
    Player context is enrichment, not a structural dependency.
    """

    path = (
        RESULTS_DIR
        / (
            f"player_wpa_v3_"
            f"{game_id}_summary.csv"
        )
    )

    if not path.exists():
        return None

    try:
        df = pd.read_csv(
            path
        )

    except Exception:
        return None

    required = {
        "player",
        "team",
        "net_wpa_pp",
    }

    if not required.issubset(
        df.columns
    ):
        return None

    return df


# ============================================================
# Game-level validation
# ============================================================

def validate_game(
    game_id,
    game_date,
    season,
):
    output = (
        io.StringIO()
    )

    with contextlib.redirect_stdout(
        output
    ):
        analysis = (
            analyze_live_game(
                game_id=game_id,
                season=season,
                game_date=game_date,
                top_k=3,
                assume_final=True,
            )
        )

    timeline = (
        analysis[
            "timeline"
        ]
    )

    home_metadata = (
        get_team_metadata(
            analysis[
                "home_team_id"
            ]
        )
    )

    away_metadata = (
        get_team_metadata(
            analysis[
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

    player_summary = (
        load_cached_player_summary(
            game_id
        )
    )

    explanations = (
        build_contextual_explanations(
            game_df=timeline,
            momentum_result=momentum,
            home_team=home_team,
            away_team=away_team,
            player_summary=player_summary,
            top_k=4,
        )
    )

    runs = (
        momentum[
            "all_runs"
        ]
    )

    rows = []

    missing_source_runs = 0

    for rank, explanation in enumerate(
        explanations,
        start=1,
    ):
        source_run = (
            find_source_run(
                explanation,
                runs,
            )
        )

        if source_run is None:
            missing_source_runs += 1

            rows.append(
                {
                    "gameId":
                        game_id,

                    "rank":
                        rank,

                    "team":
                        explanation[
                            "team"
                        ],

                    "headline":
                        explanation[
                            "headline"
                        ],

                    "structuralPass":
                        False,

                    "missingSourceRun":
                        True,
                }
            )

            continue

        result = (
            validate_explanation(
                game_id=game_id,
                rank=rank,
                explanation=explanation,
                source_run=source_run,
                home_team=home_team,
            )
        )

        result[
            "missingSourceRun"
        ] = False

        rows.append(
            result
        )

    # Determinism / ranking check:
    # contextScore must be non-increasing.
    context_scores = [
        safe_float(
            explanation[
                "contextScore"
            ]
        )
        for explanation
        in explanations
    ]

    ranking_pass = all(
        context_scores[index]
        >= context_scores[
            index + 1
        ]
        for index
        in range(
            len(context_scores)
            - 1
        )
    )

    unique_windows = {
        (
            explanation[
                "team"
            ],
            explanation[
                "startPeriod"
            ],
            str(
                explanation[
                    "startClock"
                ]
            ),
            explanation[
                "endPeriod"
            ],
            str(
                explanation[
                    "endClock"
                ]
            ),
        )
        for explanation
        in explanations
    }

    duplicate_pass = (
        len(
            unique_windows
        )
        ==
        len(
            explanations
        )
    )

    row_pass = all(
        row.get(
            "structuralPass",
            False,
        )
        for row
        in rows
    )

    game_pass = all(
        [
            row_pass,
            ranking_pass,
            duplicate_pass,
            missing_source_runs == 0,
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

        "momentumRuns":
            len(
                runs
            ),

        "explanations":
            len(
                explanations
            ),

        "playerContextAvailable":
            player_summary
            is not None,

        "explanationsWithPlayerContext":
            sum(
                bool(
                    row.get(
                        "hasPlayerContext",
                        False,
                    )
                )
                for row
                in rows
            ),

        "missingSourceRuns":
            missing_source_runs,

        "rankingPass":
            ranking_pass,

        "duplicatePass":
            duplicate_pass,

        "rowStructuralPass":
            row_pass,

        "overallPass":
            game_pass,
    }

    return (
        game_row,
        rows,
    )


# ============================================================
# CLI
# ============================================================

def parse_args():
    parser = (
        argparse.ArgumentParser(
            description=(
                "Validate Courtvision contextual "
                "game explanations."
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

    games = (
        load_game_catalog(
            args.season
        )
    )

    sample = (
        select_evenly_spaced_games(
            games,
            args.sample_size,
        )
    )

    print(
        "Courtvision Contextual Explanation Validation"
    )

    print(
        "Season:",
        args.season,
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
    explanation_rows = []
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
                explanation_result,
            ) = (
                validate_game(
                    game_id=game_id,
                    game_date=game_date,
                    season=args.season,
                )
            )

            game_rows.append(
                game_result
            )

            explanation_rows.extend(
                explanation_result
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
                        str(error),
                }
            )

    games_df = (
        pd.DataFrame(
            game_rows
        )
    )

    explanations_df = (
        pd.DataFrame(
            explanation_rows
        )
    )

    failures_df = (
        pd.DataFrame(
            failures
        )
    )

    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    games_path = (
        RESULTS_DIR
        / (
            f"contextual_{args.season}"
            "_validation_games.csv"
        )
    )

    explanations_path = (
        RESULTS_DIR
        / (
            f"contextual_{args.season}"
            "_validation_explanations.csv"
        )
    )

    failures_path = (
        RESULTS_DIR
        / (
            f"contextual_{args.season}"
            "_validation_failures.csv"
        )
    )

    games_df.to_csv(
        games_path,
        index=False,
    )

    explanations_df.to_csv(
        explanations_path,
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
            len(
                games_df
            )
            - passed,
        )

        print()

        print(
            "Explanations per game"
        )

        print(
            "  mean:",
            (
                f"{games_df['explanations'].mean():.2f}"
            ),
        )

        print(
            "  min :",
            int(
                games_df[
                    "explanations"
                ].min()
            ),
        )

        print(
            "  max :",
            int(
                games_df[
                    "explanations"
                ].max()
            ),
        )

        print()

        print(
            "Games with correct ranking:",
            int(
                games_df[
                    "rankingPass"
                ].sum()
            ),
            "/",
            len(
                games_df
            ),
        )

        print(
            "Games with no duplicate windows:",
            int(
                games_df[
                    "duplicatePass"
                ].sum()
            ),
            "/",
            len(
                games_df
            ),
        )

        print(
            "Missing source runs:",
            int(
                games_df[
                    "missingSourceRuns"
                ].sum()
            ),
        )

        print()

        total_explanations = int(
            games_df[
                "explanations"
            ].sum()
        )

        player_context = int(
            games_df[
                "explanationsWithPlayerContext"
            ].sum()
        )

        print(
            "Player-context coverage:",
            (
                f"{player_context}/"
                f"{total_explanations}"
            ),
        )

        if total_explanations:
            print(
                "  percentage:",
                (
                    f"{player_context / total_explanations * 100:.1f}%"
                ),
            )

    if not explanations_df.empty:
        print()

        print(
            "Explanation structural checks"
        )

        check_columns = [
            "scoreIdentityPass",
            "teamMatchPass",
            "opponentMatchPass",
            "swingMatchPass",
            "summaryMarginPass",
            "headlinePass",
            "structuralPass",
        ]

        for column in check_columns:
            if column not in explanations_df.columns:
                continue

            print(
                f"  {column}: "
                f"{int(explanations_df[column].sum())}/"
                f"{len(explanations_df)}"
            )

        print()

        print(
            "Top explanations by context score"
        )

        display_columns = [
            "gameId",
            "rank",
            "team",
            "headline",
            "winProbabilitySwingPoints",
            "contextScore",
            "beforeMargin",
            "afterMargin",
            "detailCount",
        ]

        available_columns = [
            column
            for column
            in display_columns
            if column
            in explanations_df.columns
        ]

        print(
            explanations_df
            .sort_values(
                "contextScore",
                ascending=False,
            )
            .head(
                12
            )[
                available_columns
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
        explanations_path,
    )

    print(
        " ",
        failures_path,
    )


if __name__ == "__main__":
    main()
