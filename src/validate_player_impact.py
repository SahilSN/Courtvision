import argparse
import contextlib
import io
from pathlib import Path

import numpy as np
import pandas as pd

from player_impact import (
    analyze_player_impact,
    normalize_game_id,
)


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
# Validation thresholds
# ============================================================

DECOMPOSITION_TOLERANCE = 1e-6

MIN_SEQUENCE_COVERAGE = 0.75

MIN_EVENT_EFFECT_COVERAGE = 0.90

MAX_REASONABLE_SINGLE_EVENT_WPA = 0.60

MIN_SCORING_SHARE_TOP_10 = 0.50


# ============================================================
# Game selection
# ============================================================

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
# Individual checks
# ============================================================

def decomposition_error(
    sequences,
):
    """
    WPA v3 should satisfy:

    observed adjacent change
      =
    time effect
      +
    counterfactual event effect
    """

    required = [
        "observedAdjacentChange",
        "timeEffect",
        "eventHomeWinProbabilityChange",
    ]

    valid = (
        sequences[
            required
        ]
        .dropna()
        .copy()
    )

    if valid.empty:
        return np.nan

    error = (
        valid[
            "observedAdjacentChange"
        ]
        - (
            valid[
                "timeEffect"
            ]
            + valid[
                "eventHomeWinProbabilityChange"
            ]
        )
    )

    return float(
        error
        .abs()
        .max()
    )


def probabilities_are_valid(
    sequences,
):
    columns = [
        "counterfactualWinProbability",
        "actualWinProbability",
    ]

    for column in columns:
        if column not in (
            sequences.columns
        ):
            return False

        values = (
            pd.to_numeric(
                sequences[
                    column
                ],
                errors="coerce",
            )
            .dropna()
        )

        if values.empty:
            continue

        if not np.isfinite(
            values
        ).all():
            return False

        if (
            (
                values < 0
            )
            | (
                values > 1
            )
        ).any():
            return False

    return True


def event_values_are_finite(
    events,
):
    if events.empty:
        return True

    values = (
        pd.to_numeric(
            events[
                "playerWPA"
            ],
            errors="coerce",
        )
    )

    return bool(
        values.notna().all()
        and np.isfinite(
            values
        ).all()
    )


def largest_event_wpa(
    events,
):
    if events.empty:
        return np.nan

    if (
        "sourcePlayerWPA"
        in events.columns
    ):
        values = pd.to_numeric(
            events[
                "sourcePlayerWPA"
            ],
            errors="coerce",
        )

    else:
        values = pd.to_numeric(
            events[
                "playerWPA"
            ],
            errors="coerce",
        )

    values = (
        values
        .dropna()
        .abs()
    )

    if values.empty:
        return np.nan

    return float(
        values.max()
    )



def scoring_share_of_top_events(
    events,
    n=10,
):
    """
    Measure the share of the largest underlying
    WPA sequences that are scoring plays.

    Shared-credit attribution can create multiple
    player-allocation rows from one basketball
    sequence, so validation must collapse back to
    one row per sequence before ranking events.
    """

    if events.empty:
        return np.nan

    df = (
        events.copy()
    )

    # sourcePlayerWPA preserves the original
    # pre-split WPA value. Fall back to playerWPA
    # for compatibility with primary-only WPA v3.
    if (
        "sourcePlayerWPA"
        in df.columns
    ):
        df[
            "validationEventWPA"
        ] = pd.to_numeric(
            df[
                "sourcePlayerWPA"
            ],
            errors="coerce",
        )

    else:
        df[
            "validationEventWPA"
        ] = pd.to_numeric(
            df[
                "playerWPA"
            ],
            errors="coerce",
        )

    df[
        "absoluteEventWPA"
    ] = (
        df[
            "validationEventWPA"
        ]
        .abs()
    )

    # Collapse scorer/assister, turnover/stealer,
    # and shooter/blocker allocations back into
    # their original sequence.
    sequence_events = (
        df.sort_values(
            "absoluteEventWPA",
            ascending=False,
        )
        .drop_duplicates(
            subset=[
                "sequenceId",
            ],
            keep="first",
        )
    )

    top = (
        sequence_events.nlargest(
            min(
                n,
                len(
                    sequence_events
                ),
            ),
            "absoluteEventWPA",
        )
    )

    if top.empty:
        return np.nan

    return float(
        (
            top[
                "attributionType"
            ]
            == "Scoring"
        )
        .mean()
    )



def same_clock_grouping_rate(
    sequences,
):
    if sequences.empty:
        return np.nan

    return float(
        (
            sequences[
                "rowsInSequence"
            ]
            > 1
        )
        .mean()
    )


def player_total_diagnostics(
    summary,
):
    if summary.empty:
        return {
            "max_player_net_wpa":
                np.nan,

            "min_player_net_wpa":
                np.nan,

            "max_player_absolute_wpa":
                np.nan,
        }

    return {
        "max_player_net_wpa":
            float(
                summary[
                    "netWPA"
                ].max()
            ),

        "min_player_net_wpa":
            float(
                summary[
                    "netWPA"
                ].min()
            ),

        "max_player_absolute_wpa":
            float(
                summary[
                    "absoluteWPA"
                ].max()
            ),
    }


# ============================================================
# Validate one game
# ============================================================

def validate_game(
    game_id,
    game_date,
    season,
):
    normalized_id = (
        normalize_game_id(
            game_id
        )
    )

    # player_impact.py currently prints a
    # human-readable report. Suppress that
    # while running batch validation.
    buffer = io.StringIO()

    with contextlib.redirect_stdout(
        buffer
    ):
        result = (
            analyze_player_impact(
                game_id=normalized_id,
                season=season,
                top_k=10,
            )
        )

    events = (
        result[
            "events"
        ]
    )

    sequences = (
        result[
            "sequences"
        ]
    )

    summary = (
        result[
            "player_summary"
        ]
    )

    diagnostics = (
        result[
            "diagnostics"
        ]
    )

    max_decomposition_error = (
        decomposition_error(
            sequences
        )
    )

    probability_check = (
        probabilities_are_valid(
            sequences
        )
    )

    finite_event_check = (
        event_values_are_finite(
            events
        )
    )

    max_event = (
        largest_event_wpa(
            events
        )
    )

    scoring_share = (
        scoring_share_of_top_events(
            events,
            n=10,
        )
    )

    grouping_rate = (
        same_clock_grouping_rate(
            sequences
        )
    )

    player_diagnostics = (
        player_total_diagnostics(
            summary
        )
    )

    sequence_coverage = float(
        diagnostics[
            "sequence_coverage"
        ]
    )

    event_effect_coverage = float(
        diagnostics[
            "event_effect_coverage"
        ]
    )

    decomposition_pass = (
        np.isnan(
            max_decomposition_error
        )
        or (
            max_decomposition_error
            <= DECOMPOSITION_TOLERANCE
        )
    )

    sequence_coverage_pass = (
        sequence_coverage
        >= MIN_SEQUENCE_COVERAGE
    )

    event_coverage_pass = (
        event_effect_coverage
        >= MIN_EVENT_EFFECT_COVERAGE
    )

    event_size_pass = (
        np.isnan(
            max_event
        )
        or (
            max_event
            <= MAX_REASONABLE_SINGLE_EVENT_WPA
        )
    )

    scoring_share_pass = (
        np.isnan(
            scoring_share
        )
        or (
            scoring_share
            >= MIN_SCORING_SHARE_TOP_10
        )
    )

    overall_pass = all(
        [
            decomposition_pass,
            probability_check,
            finite_event_check,
            sequence_coverage_pass,
            event_coverage_pass,
            event_size_pass,
            scoring_share_pass,
        ]
    )

    row = {
        "gameId":
            normalized_id,

        "gameDate":
            game_date,

        "homeTeam":
            result[
                "home_team"
            ],

        "awayTeam":
            result[
                "away_team"
            ],

        "clockSequences":
            diagnostics[
                "clock_sequences"
            ],

        "attributedSequences":
            diagnostics[
                "attributed_sequences"
            ],

        "sequenceCoverage":
            sequence_coverage,

        "eventEffectCoverage":
            event_effect_coverage,

        "absoluteAdjacentMovement":
            diagnostics[
                "absolute_adjacent_change"
            ],

        "absoluteCounterfactualEventEffect":
            diagnostics[
                "absolute_event_effect"
            ],

        "absoluteClockEffect":
            diagnostics[
                "absolute_time_effect"
            ],

        "maxDecompositionError":
            max_decomposition_error,

        "probabilitiesValid":
            probability_check,

        "eventValuesFinite":
            finite_event_check,

        "maxAbsoluteEventWPA":
            max_event,

        "top10ScoringShare":
            scoring_share,

        "sameClockGroupingRate":
            grouping_rate,

        **player_diagnostics,

        "decompositionPass":
            decomposition_pass,

        "sequenceCoveragePass":
            sequence_coverage_pass,

        "eventCoveragePass":
            event_coverage_pass,

        "eventSizePass":
            event_size_pass,

        "scoringSharePass":
            scoring_share_pass,

        "overallPass":
            overall_pass,
    }

    return row


# ============================================================
# Event-type diagnostics
# ============================================================

def summarize_event_types(
    event_frames,
):
    if not event_frames:
        return pd.DataFrame()

    events = pd.concat(
        event_frames,
        ignore_index=True,
    )

    if events.empty:
        return pd.DataFrame()

    events[
        "absoluteWPA"
    ] = (
        events[
            "playerWPA"
        ]
        .abs()
    )

    summary = (
        events.groupby(
            "attributionType"
        )
        .agg(
            events=(
                "playerWPA",
                "size",
            ),

            meanWPA=(
                "playerWPA",
                "mean",
            ),

            meanAbsoluteWPA=(
                "absoluteWPA",
                "mean",
            ),

            maxAbsoluteWPA=(
                "absoluteWPA",
                "max",
            ),
        )
        .reset_index()
        .sort_values(
            "events",
            ascending=False,
        )
        .reset_index(
            drop=True
        )
    )

    return summary


# ============================================================
# Main
# ============================================================

def parse_args():
    parser = (
        argparse.ArgumentParser(
            description=(
                "Validate Courtvision WPA v3 "
                "across a deterministic sample "
                "of NBA games."
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
        default=20,
    )

    return parser.parse_args()


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
        "Courtvision WPA v3 validation"
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

    validation_rows = []
    event_frames = []
    failures = []

    for index, row in (
        sample.iterrows()
    ):
        game_id = (
            normalize_game_id(
                row[
                    "gameId"
                ]
            )
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
            validation = (
                validate_game(
                    game_id,
                    game_date,
                    season,
                )
            )

            validation_rows.append(
                validation
            )

            # Load the generated WPA event
            # file for cross-game event-type
            # diagnostics.
            event_path = (
                RESULTS_DIR
                / (
                    "player_wpa_v3_"
                    f"{game_id}"
                    "_events.csv"
                )
            )

            if event_path.exists():
                event_df = (
                    pd.read_csv(
                        event_path
                    )
                )

                event_df[
                    "gameId"
                ] = game_id

                event_frames.append(
                    event_df
                )

            if validation[
                "overallPass"
            ]:
                print(
                    "PASS"
                )
            else:
                print(
                    "REVIEW"
                )

        except Exception as error:
            print(
                "FAILED"
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

    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    validation_df = (
        pd.DataFrame(
            validation_rows
        )
    )

    validation_path = (
        RESULTS_DIR
        / (
            f"wpa_v3_{season}"
            "_validation_games.csv"
        )
    )

    validation_df.to_csv(
        validation_path,
        index=False,
    )

    event_type_df = (
        summarize_event_types(
            event_frames
        )
    )

    event_type_path = (
        RESULTS_DIR
        / (
            f"wpa_v3_{season}"
            "_event_types.csv"
        )
    )

    event_type_df.to_csv(
        event_type_path,
        index=False,
    )

    failures_df = (
        pd.DataFrame(
            failures
        )
    )

    failure_path = (
        RESULTS_DIR
        / (
            f"wpa_v3_{season}"
            "_validation_failures.csv"
        )
    )

    failures_df.to_csv(
        failure_path,
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
            validation_df
        ),
    )

    print(
        "Failures:",
        len(
            failures_df
        ),
    )

    if not validation_df.empty:
        passed = int(
            validation_df[
                "overallPass"
            ].sum()
        )

        review = (
            len(
                validation_df
            )
            - passed
        )

        print(
            "PASS:",
            passed,
        )

        print(
            "REVIEW:",
            review,
        )

        print()

        print(
            "Sequence coverage"
        )

        print(
            "  mean:",
            (
                f"{validation_df['sequenceCoverage'].mean() * 100:.1f}%"
            ),
        )

        print(
            "  min :",
            (
                f"{validation_df['sequenceCoverage'].min() * 100:.1f}%"
            ),
        )

        print()

        print(
            "Event-effect coverage"
        )

        print(
            "  mean:",
            (
                f"{validation_df['eventEffectCoverage'].mean() * 100:.1f}%"
            ),
        )

        print(
            "  min :",
            (
                f"{validation_df['eventEffectCoverage'].min() * 100:.1f}%"
            ),
        )

        print()

        print(
            "Decomposition error"
        )

        print(
            "  max:",
            (
                f"{validation_df['maxDecompositionError'].max():.3e}"
            ),
        )

        print()

        print(
            "Largest single-event WPA"
        )

        print(
            "  mean:",
            (
                f"{validation_df['maxAbsoluteEventWPA'].mean() * 100:.2f} pp"
            ),
        )

        print(
            "  max :",
            (
                f"{validation_df['maxAbsoluteEventWPA'].max() * 100:.2f} pp"
            ),
        )

        print()

        print(
            "Top-10 scoring-event share"
        )

        print(
            "  mean:",
            (
                f"{validation_df['top10ScoringShare'].mean() * 100:.1f}%"
            ),
        )

        print(
            "  min :",
            (
                f"{validation_df['top10ScoringShare'].min() * 100:.1f}%"
            ),
        )

        print()

        print(
            "Same-clock grouping rate"
        )

        print(
            "  mean:",
            (
                f"{validation_df['sameClockGroupingRate'].mean() * 100:.1f}%"
            ),
        )

    print()

    if not event_type_df.empty:
        print(
            "Event-type summary"
        )

        print(
            event_type_df.to_string(
                index=False,
                float_format=(
                    lambda value:
                        f"{value:.4f}"
                ),
            )
        )

    print()

    print(
        "Saved:"
    )

    print(
        " ",
        validation_path,
    )

    print(
        " ",
        event_type_path,
    )

    print(
        " ",
        failure_path,
    )


if __name__ == "__main__":
    main()
