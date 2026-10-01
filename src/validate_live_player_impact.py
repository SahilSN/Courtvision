from pathlib import Path

import numpy as np
import pandas as pd

from live_analysis import (
    analyze_live_game,
)

from player_impact import (
    analyze_player_impact,
    analyze_player_impact_from_game_df,
)


ROOT_DIR = (
    Path(__file__)
    .resolve()
    .parents[1]
)

RESULTS_DIR = (
    ROOT_DIR
    / "results"
)

GAME_ID = "0022501188"
SEASON = "2025-26"

CHECKPOINTS = [
    (
        "End Q1",
        720.0,
    ),
    (
        "Halftime",
        1440.0,
    ),
    (
        "End Q3",
        2160.0,
    ),
    (
        "6:00 Q4",
        2520.0,
    ),
    (
        "End regulation",
        2880.0,
    ),
]


def get_game_date():
    path = (
        ROOT_DIR
        / "data"
        / "training"
        / f"{SEASON}_training_v4_base.csv"
    )

    df = pd.read_csv(
        path,
        usecols=[
            "gameId",
            "gameDate",
        ],
    )

    game_id_int = int(
        GAME_ID
    )

    rows = df.loc[
        df[
            "gameId"
        ].astype(int)
        == game_id_int
    ]

    if rows.empty:
        raise RuntimeError(
            f"Could not find {GAME_ID} "
            f"in {path}."
        )

    return str(
        rows[
            "gameDate"
        ].iloc[0]
    )


def canonical_summary(
    summary,
):
    if summary.empty:
        return summary.copy()

    columns = [
        column
        for column
        in [
            "player",
            "team",
            "events",
            "net_wpa",
            "positive_wpa",
            "negative_wpa",
            "absolute_wpa",
            "net_wpa_pp",
            "positive_wpa_pp",
            "negative_wpa_pp",
            "absolute_wpa_pp",
        ]
        if column
        in summary.columns
    ]

    result = (
        summary[
            columns
        ]
        .copy()
    )

    sort_columns = [
        column
        for column
        in [
            "team",
            "player",
        ]
        if column
        in result.columns
    ]

    if sort_columns:
        result = (
            result
            .sort_values(
                sort_columns,
                kind="mergesort",
            )
            .reset_index(
                drop=True
            )
        )

    return result


def compare_summaries(
    first,
    second,
    atol=1e-9,
):
    first = canonical_summary(
        first
    )

    second = canonical_summary(
        second
    )

    if (
        list(first.columns)
        != list(second.columns)
    ):
        return (
            False,
            "column mismatch",
        )

    if len(first) != len(second):
        return (
            False,
            (
                f"row mismatch "
                f"{len(first)} vs {len(second)}"
            ),
        )

    for column in first.columns:
        left = first[
            column
        ]

        right = second[
            column
        ]

        if pd.api.types.is_numeric_dtype(
            left
        ):
            if not np.allclose(
                pd.to_numeric(
                    left,
                    errors="coerce",
                ),
                pd.to_numeric(
                    right,
                    errors="coerce",
                ),
                atol=atol,
                rtol=0.0,
                equal_nan=True,
            ):
                return (
                    False,
                    f"value mismatch in {column}",
                )

        else:
            if not (
                left.astype(str)
                .to_numpy()
                ==
                right.astype(str)
                .to_numpy()
            ).all():
                return (
                    False,
                    f"value mismatch in {column}",
                )

    return (
        True,
        "exact",
    )


def main():
    game_date = (
        get_game_date()
    )

    print(
        "Live Player Impact Validation"
    )

    print(
        "Game:",
        GAME_ID,
    )

    print(
        "Season:",
        SEASON,
    )

    print(
        "Date:",
        game_date,
    )

    print()

    checkpoint_results = {}

    for (
        label,
        cutoff,
    ) in CHECKPOINTS:
        live_result = (
            analyze_live_game(
                game_id=GAME_ID,
                season=SEASON,
                game_date=game_date,
                assume_final=False,
                replay_cutoff_elapsed=cutoff,
            )
        )

        game_df = (
            live_result[
                "timeline"
            ]
            .copy()
        )

        impact = (
            analyze_player_impact_from_game_df(
                game_df,
                top_k=10,
            )
        )

        rerun = (
            analyze_player_impact_from_game_df(
                game_df,
                top_k=10,
            )
        )

        deterministic, reason = (
            compare_summaries(
                impact[
                    "summary"
                ],
                rerun[
                    "summary"
                ],
            )
        )

        events = (
            impact[
                "events"
            ]
        )

        sequences = (
            impact[
                "sequence_table"
            ]
        )

        max_event_elapsed = (
            float(
                pd.to_numeric(
                    events[
                        "elapsedGameTime"
                    ],
                    errors="coerce",
                )
                .max()
            )
            if (
                not events.empty
                and
                "elapsedGameTime"
                in events.columns
            )
            else float("nan")
        )

        max_sequence_elapsed = (
            float(
                pd.to_numeric(
                    sequences[
                        "elapsedGameTime"
                    ],
                    errors="coerce",
                )
                .max()
            )
            if (
                not sequences.empty
                and
                "elapsedGameTime"
                in sequences.columns
            )
            else float("nan")
        )

        no_future_events = (
            np.isnan(
                max_event_elapsed
            )
            or
            max_event_elapsed
            <= cutoff + 1e-9
        )

        no_future_sequences = (
            np.isnan(
                max_sequence_elapsed
            )
            or
            max_sequence_elapsed
            <= cutoff + 1e-9
        )

        checkpoint_results[
            label
        ] = impact

        print(
            f"{label:<16} "
            f"| rows={len(game_df):4d} "
            f"| events={len(events):3d} "
            f"| players={len(impact['summary']):2d} "
            f"| future_events={'PASS' if no_future_events else 'FAIL'} "
            f"| future_sequences={'PASS' if no_future_sequences else 'FAIL'} "
            f"| deterministic={'PASS' if deterministic else 'FAIL'}"
        )

        if not deterministic:
            print(
                "  Determinism:",
                reason,
            )

        if not (
            no_future_events
            and no_future_sequences
            and deterministic
        ):
            raise RuntimeError(
                f"{label} replay validation failed."
            )

    print()
    print(
        "Running frozen historical WPA..."
    )

    historical = (
        analyze_player_impact(
            game_id=GAME_ID,
            season=SEASON,
            top_k=10,
        )
    )

    final_impact = (
        checkpoint_results[
            "End regulation"
        ]
    )

    historical_summary_path = (
        RESULTS_DIR
        / (
            f"player_wpa_v3_"
            f"{GAME_ID}"
            "_summary.csv"
        )
    )

    historical_summary = pd.read_csv(
        historical_summary_path
    )

    exact, reason = (
        compare_summaries(
            final_impact[
                "summary"
            ],
            historical_summary,
        )
    )

    print()
    print(
        "Final replay vs frozen historical:",
        (
            "PASS"
            if exact
            else "FAIL"
        ),
    )

    if not exact:
        print(
            "Reason:",
            reason,
        )

        final_path = (
            RESULTS_DIR
            / "live_player_impact_final_summary.csv"
        )

        historical_path = (
            RESULTS_DIR
            / "live_player_impact_historical_summary.csv"
        )

        canonical_summary(
            final_impact[
                "summary"
            ]
        ).to_csv(
            final_path,
            index=False,
        )

        canonical_summary(
            historical_summary
        ).to_csv(
            historical_path,
            index=False,
        )

        raise RuntimeError(
            "Final replay WPA does not match "
            "frozen historical WPA."
        )

    print()
    print(
        "✓ Live Player Impact replay validation passed."
    )


if __name__ == "__main__":
    main()
