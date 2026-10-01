import argparse

import numpy as np

from live_analysis import (
    analyze_live_game,
)


CHECKPOINTS = [
    ("End Q1", 720),
    ("Halftime", 1440),
    ("End Q3", 2160),
    ("6:00 Q4", 2520),
    ("End regulation", 2880),
]


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--game-id",
        required=True,
    )

    parser.add_argument(
        "--season",
        required=True,
    )

    parser.add_argument(
        "--game-date",
        required=True,
    )

    return parser.parse_args()


def main():
    args = parse_args()

    full = analyze_live_game(
        game_id=args.game_id,
        season=args.season,
        game_date=args.game_date,
        top_k=3,
        assume_final=True,
    )

    full_timeline = (
        full["timeline"]
        .copy()
        .reset_index(
            drop=True
        )
    )

    previous_rows = 0

    print(
        "Historical live-replay validation"
    )

    print(
        f"Game: {args.game_id}"
    )

    print()

    for label, cutoff in CHECKPOINTS:
        replay = analyze_live_game(
            game_id=args.game_id,
            season=args.season,
            game_date=args.game_date,
            top_k=3,
            assume_final=False,
            replay_cutoff_elapsed=cutoff,
        )

        timeline = (
            replay["timeline"]
            .copy()
            .reset_index(
                drop=True
            )
        )

        if timeline.empty:
            raise AssertionError(
                f"{label}: empty replay timeline."
            )

        max_elapsed = float(
            timeline[
                "elapsedGameTime"
            ].max()
        )

        if max_elapsed > cutoff:
            raise AssertionError(
                f"{label}: future state leaked "
                f"({max_elapsed} > {cutoff})."
            )

        if len(timeline) < previous_rows:
            raise AssertionError(
                f"{label}: replay timeline shrank."
            )

        previous_rows = len(
            timeline
        )

        matching_full = (
            full_timeline.loc[
                full_timeline[
                    "elapsedGameTime"
                ]
                <= cutoff
            ]
            .reset_index(
                drop=True
            )
        )

        if len(
            timeline
        ) != len(
            matching_full
        ):
            raise AssertionError(
                f"{label}: row mismatch: "
                f"{len(timeline)} replay vs "
                f"{len(matching_full)} full prefix."
            )

        replay_wp = (
            timeline[
                "winProbability"
            ]
            .astype(
                float
            )
            .to_numpy()
        )

        full_wp = (
            matching_full[
                "winProbability"
            ]
            .astype(
                float
            )
            .to_numpy()
        )

        if not np.allclose(
            replay_wp,
            full_wp,
            rtol=0.0,
            atol=1e-6,
            equal_nan=True,
        ):
            differences = np.abs(
                replay_wp
                - full_wp
            )

            max_index = int(
                np.nanargmax(
                    differences
                )
            )

            print()
            print(
                f"{label}: prediction mismatch"
            )

            print(
                "Max WP difference:",
                differences[
                    max_index
                ],
            )

            print(
                "Replay WP:",
                replay_wp[
                    max_index
                ],
            )

            print(
                "Full WP:",
                full_wp[
                    max_index
                ],
            )

            print(
                "Elapsed:",
                timeline.iloc[
                    max_index
                ][
                    "elapsedGameTime"
                ],
            )

            feature_columns = [
                "elapsedGameTime",
                "homeScoreDiff",
                "homePossession",
                "totalScore",
                "homePreGameWinPct",
                "awayPreGameWinPct",
                "strengthDifference",
                "scoreDiffLateWeight",
            ]

            print()
            print(
                "Replay features:"
            )

            print(
                timeline.iloc[
                    max_index
                ][
                    feature_columns
                ]
            )

            print()
            print(
                "Full features:"
            )

            print(
                matching_full.iloc[
                    max_index
                ][
                    feature_columns
                ]
            )

            print()
            print(
                "Feature equality:"
            )

            for column in feature_columns:
                replay_value = (
                    timeline.iloc[
                        max_index
                    ][column]
                )

                full_value = (
                    matching_full.iloc[
                        max_index
                    ][column]
                )

                print(
                    f"{column}: "
                    f"{replay_value!r} vs "
                    f"{full_value!r}"
                )

            raise AssertionError(
                f"{label}: historical-prefix "
                "predictions changed."
            )

        print(
            f"{label:16s} | "
            f"rows={len(timeline):4d} | "
            f"elapsed={max_elapsed:7.1f} | "
            f"current WP="
            f"{replay['current_home_win_probability']:.3f}"
        )

    print()
    print(
        "✓ Live replay validation passed."
    )


if __name__ == "__main__":
    main()
