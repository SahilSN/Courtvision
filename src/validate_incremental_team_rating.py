from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from incremental_team_rating import (
    HISTORY_COLUMNS,
    run_incremental_update,
)


ROOT_DIR = (
    Path(__file__)
    .resolve()
    .parents[1]
)


FLOAT_COLUMNS = [
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


EXACT_COLUMNS = [
    "season",
    "gameDate",
    "gameId",
    "homeTeam",
    "awayTeam",
    "homeWin",
    "winner",
]


def normalize(
    df,
):
    df = df.copy()

    df[
        "gameId"
    ] = (
        df[
            "gameId"
        ]
        .astype(
            str
        )
        .str.zfill(
            10
        )
    )

    df[
        "_sortDate"
    ] = pd.to_datetime(
        df[
            "gameDate"
        ],
        errors="raise",
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


def compare_histories(
    incremental,
    batch,
):
    incremental = normalize(
        incremental[
            HISTORY_COLUMNS
        ]
    )

    batch = normalize(
        batch[
            HISTORY_COLUMNS
        ]
    )

    if len(
        incremental
    ) != len(
        batch
    ):
        raise AssertionError(
            "History row-count mismatch: "
            f"incremental={len(incremental)}, "
            f"batch={len(batch)}"
        )

    for column in EXACT_COLUMNS:
        left = (
            incremental[
                column
            ]
            .astype(
                str
            )
        )

        right = (
            batch[
                column
            ]
            .astype(
                str
            )
        )

        if not left.equals(
            right
        ):
            mismatch = np.flatnonzero(
                left.to_numpy()
                != right.to_numpy()
            )

            first = int(
                mismatch[
                    0
                ]
            )

            raise AssertionError(
                f"Exact mismatch in {column} "
                f"at row {first}: "
                f"{left.iloc[first]!r} != "
                f"{right.iloc[first]!r}"
            )

    for column in FLOAT_COLUMNS:
        left = pd.to_numeric(
            incremental[
                column
            ],
            errors="raise",
        ).to_numpy(
            dtype=float
        )

        right = pd.to_numeric(
            batch[
                column
            ],
            errors="raise",
        ).to_numpy(
            dtype=float
        )

        if not np.allclose(
            left,
            right,
            rtol=0.0,
            atol=1e-12,
            equal_nan=True,
        ):
            diff = np.abs(
                left
                - right
            )

            first = int(
                np.nanargmax(
                    diff
                )
            )

            raise AssertionError(
                f"Float mismatch in {column}. "
                f"max_diff={diff[first]:.16g}; "
                f"row={first}; "
                f"incremental={left[first]:.16g}; "
                f"batch={right[first]:.16g}"
            )


def validate_idempotence(
    season,
    games,
    runtime_root,
):
    history_before, ratings_before, _ = (
        run_incremental_update(
            season=season,
            games=games,
            runtime_root=runtime_root,
        )
    )

    history_after, ratings_after, _ = (
        run_incremental_update(
            season=season,
            games=games,
            runtime_root=runtime_root,
        )
    )

    if len(
        history_before
    ) != len(
        history_after
    ):
        raise AssertionError(
            "Idempotence failure: history length "
            "changed after replay."
        )

    before_ids = (
        history_before[
            "gameId"
        ]
        .astype(
            str
        )
        .tolist()
    )

    after_ids = (
        history_after[
            "gameId"
        ]
        .astype(
            str
        )
        .tolist()
    )

    if before_ids != after_ids:
        raise AssertionError(
            "Idempotence failure: history IDs changed."
        )

    rating_columns = [
        "team",
        "wins",
        "losses",
        "currentRating",
        "peakRating",
        "lowestRating",
    ]

    before = (
        ratings_before[
            rating_columns
        ]
        .sort_values(
            "team"
        )
        .reset_index(
            drop=True
        )
    )

    after = (
        ratings_after[
            rating_columns
        ]
        .sort_values(
            "team"
        )
        .reset_index(
            drop=True
        )
    )

    if not (
        before[
            [
                "team",
                "wins",
                "losses",
            ]
        ]
        .equals(
            after[
                [
                    "team",
                    "wins",
                    "losses",
                ]
            ]
        )
    ):
        raise AssertionError(
            "Idempotence failure in team records."
        )

    for column in [
        "currentRating",
        "peakRating",
        "lowestRating",
    ]:
        if not np.allclose(
            before[
                column
            ].to_numpy(
                dtype=float
            ),
            after[
                column
            ].to_numpy(
                dtype=float
            ),
            rtol=0.0,
            atol=1e-12,
        ):
            raise AssertionError(
                f"Idempotence failure in {column}."
            )


def validate_recovery_from_history(
    season,
    games,
    batch_history,
):
    with tempfile.TemporaryDirectory(
        prefix=(
            "courtvision_incremental_recovery_"
        )
    ) as temp_dir:
        runtime_root = Path(
            temp_dir
        )

        history, ratings_before, paths = (
            run_incremental_update(
                season=season,
                games=games,
                runtime_root=runtime_root,
            )
        )

        for key in [
            "state",
            "ratings",
            "teamGames",
        ]:
            artifact_path = Path(
                paths[
                    key
                ]
            )

            if artifact_path.exists():
                artifact_path.unlink()

        recovered_history, ratings_after, recovered_paths = (
            run_incremental_update(
                season=season,
                games=games,
                runtime_root=runtime_root,
            )
        )

        compare_histories(
            incremental=(
                recovered_history
            ),
            batch=(
                batch_history
            ),
        )

        before = (
            ratings_before
            .sort_values(
                "team"
            )
            .reset_index(
                drop=True
            )
        )

        after = (
            ratings_after
            .sort_values(
                "team"
            )
            .reset_index(
                drop=True
            )
        )

        if not (
            before[
                [
                    "team",
                    "wins",
                    "losses",
                ]
            ]
            .equals(
                after[
                    [
                        "team",
                        "wins",
                        "losses",
                    ]
                ]
            )
        ):
            raise AssertionError(
                "Recovery changed team records."
            )

        for column in [
            "currentRating",
            "peakRating",
            "lowestRating",
        ]:
            if not np.allclose(
                before[
                    column
                ].to_numpy(
                    dtype=float
                ),
                after[
                    column
                ].to_numpy(
                    dtype=float
                ),
                rtol=0.0,
                atol=1e-12,
            ):
                raise AssertionError(
                    f"Recovery changed {column}."
                )

        for key in [
            "state",
            "ratings",
            "teamGames",
        ]:
            if not Path(
                recovered_paths[
                    key
                ]
            ).exists():
                raise AssertionError(
                    f"Recovery failed to recreate {key}."
                )



def validate_chunked_replay(
    season,
    games,
    batch_history,
):
    with tempfile.TemporaryDirectory(
        prefix=(
            "courtvision_incremental_chunked_"
        )
    ) as temp_dir:
        runtime_root = Path(
            temp_dir
        )

        cut_points = [
            1,
            17,
            83,
            250,
            600,
            len(
                games
            ),
        ]

        start = 0

        history = None

        for stop in cut_points:
            stop = min(
                stop,
                len(
                    games
                ),
            )

            if stop <= start:
                continue

            chunk = (
                games.iloc[
                    start:stop
                ]
                .copy()
            )

            history, _, _ = (
                run_incremental_update(
                    season=season,
                    games=chunk,
                    runtime_root=runtime_root,
                )
            )

            start = stop

        if start < len(
            games
        ):
            history, _, _ = (
                run_incremental_update(
                    season=season,
                    games=(
                        games.iloc[
                            start:
                        ]
                        .copy()
                    ),
                    runtime_root=runtime_root,
                )
            )

        compare_histories(
            incremental=history,
            batch=batch_history,
        )


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Verify incremental Courtvision Rating "
            "against frozen batch history."
        )
    )

    parser.add_argument(
        "--season",
        default="2025-26",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    season = args.season

    games_path = (
        ROOT_DIR
        / "results"
        / "season_intelligence"
        / (
            f"{season}_"
            "game_features_v1.csv"
        )
    )

    batch_history_path = (
        ROOT_DIR
        / "results"
        / "team_rating"
        / (
            f"{season}_"
            "courtvision_rating_history_v1.csv"
        )
    )

    if not games_path.exists():
        raise FileNotFoundError(
            games_path
        )

    if not batch_history_path.exists():
        raise FileNotFoundError(
            batch_history_path
        )

    games = pd.read_csv(
        games_path,
        dtype={
            "gameId":
                str,
        },
    )

    batch_history = pd.read_csv(
        batch_history_path,
        dtype={
            "gameId":
                str,
        },
    )

    games = normalize(
        games
    )

    print(
        f"Season: {season}"
    )

    print(
        f"Games: {len(games):,}"
    )

    print()

    # --------------------------------------------------------
    # Test 1:
    # One-shot incremental replay == frozen batch
    # --------------------------------------------------------

    with tempfile.TemporaryDirectory(
        prefix=(
            "courtvision_incremental_full_"
        )
    ) as temp_dir:
        runtime_root = Path(
            temp_dir
        )

        incremental_history, _, _ = (
            run_incremental_update(
                season=season,
                games=games,
                runtime_root=runtime_root,
            )
        )

        compare_histories(
            incremental=(
                incremental_history
            ),
            batch=(
                batch_history
            ),
        )

        print(
            "✓ Full replay matches frozen batch "
            "history to 1e-12."
        )

        # ----------------------------------------------------
        # Test 2:
        # Same input a second time changes nothing
        # ----------------------------------------------------

        validate_idempotence(
            season=season,
            games=games,
            runtime_root=runtime_root,
        )

        print(
            "✓ Idempotence test passed."
        )

    # --------------------------------------------------------
    # Test 3:
    # Arbitrary incremental chunks produce same result
    # --------------------------------------------------------

    validate_chunked_replay(
        season=season,
        games=games,
        batch_history=batch_history,
    )

    print(
        "✓ Chunked replay matches frozen batch."
    )

    validate_recovery_from_history(
        season=season,
        games=games,
        batch_history=batch_history,
    )

    print(
        "✓ Recovery from canonical history passed."
    )

    print()
    print(
        "✓ INCREMENTAL TEAM RATING VALIDATION PASSED"
    )


if __name__ == "__main__":
    main()
