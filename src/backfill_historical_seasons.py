from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT_DIR = (
    Path(__file__)
    .resolve()
    .parents[1]
)

SRC_DIR = (
    ROOT_DIR
    / "src"
)

DEFAULT_SEASONS = [
    "2022-23",
    "2021-22",
    "2020-21",
    "2019-20",
]


def completed(
    season,
):
    result_dir = (
        ROOT_DIR
        / "results"
        / "season_intelligence"
    )

    required = [
        result_dir
        / f"{season}_game_features_v1.csv",

        result_dir
        / f"{season}_team_summary_v1.csv",

        result_dir
        / f"{season}_team_rating_games_v1.csv",
    ]

    return all(
        path.exists()
        for path in required
    )


def run_season(
    season,
    sleep_seconds,
):
    if completed(
        season
    ):
        print()
        print(
            f"✓ {season} already complete — skipping."
        )
        return

    command = [
        sys.executable,
        str(
            SRC_DIR
            / "backfill_season_intelligence.py"
        ),
        "--season",
        season,
        "--fetch-missing",
        "--sleep-seconds",
        str(
            sleep_seconds
        ),
    ]

    print()
    print(
        "=" * 72
    )
    print(
        f"BACKFILLING {season}"
    )
    print(
        "=" * 72
    )

    subprocess.run(
        command,
        cwd=ROOT_DIR,
        check=True,
    )


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--seasons",
        nargs="*",
        default=DEFAULT_SEASONS,
    )

    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.5,
    )

    return parser.parse_args()


def main():
    args = parse_args()

    for season in args.seasons:
        run_season(
            season=season,
            sleep_seconds=args.sleep_seconds,
        )

    print()
    print(
        "=" * 72
    )
    print(
        "✓ ALL REQUESTED HISTORICAL SEASONS COMPLETE"
    )
    print(
        "=" * 72
    )


if __name__ == "__main__":
    main()
