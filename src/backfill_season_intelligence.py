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


def run_command(
    label,
    command,
):
    print()
    print(
        "=" * 72
    )

    print(
        label
    )

    print(
        "=" * 72
    )

    print(
        " ".join(
            str(
                part
            )
            for part in command
        )
    )

    subprocess.run(
        command,
        cwd=ROOT_DIR,
        check=True,
    )


def backfill_season(
    season,
    fetch_missing=False,
    sleep_seconds=0.5,
):
    base_path = (
        ROOT_DIR
        / "data"
        / "training"
        / (
            f"{season}_"
            "training_v4_base.csv"
        )
    )

    if not base_path.exists():
        if not fetch_missing:
            raise FileNotFoundError(
                "Missing historical base dataset: "
                f"{base_path}\n\n"
                "Run with --fetch-missing to build it."
            )

        run_command(
            (
                f"Fetch + preprocess "
                f"{season}"
            ),
            [
                sys.executable,
                str(
                    SRC_DIR
                    / "fetch_season.py"
                ),
                "--season",
                season,
                "--sleep-seconds",
                str(
                    sleep_seconds
                ),
            ],
        )

    run_command(
        (
            f"Stage 1 — Season Intelligence "
            f"{season}"
        ),
        [
            sys.executable,
            str(
                SRC_DIR
                / "season_intelligence.py"
            ),
            "--season",
            season,
        ],
    )

    run_command(
        (
            f"Stage 3 — Frozen Team "
            f"Courtvision Rating {season}"
        ),
        [
            sys.executable,
            str(
                SRC_DIR
                / "courtvision_rating.py"
            ),
            "--season",
            season,
            "--margin-scale",
            "40",
            "--margin-weight",
            "1.0",
            "--alpha",
            "1.0",
        ],
    )

    run_command(
        (
            f"Stage 4 — Team Season "
            f"Intelligence {season}"
        ),
        [
            sys.executable,
            str(
                SRC_DIR
                / "team_season_intelligence.py"
            ),
            "--season",
            season,
        ],
    )

    summary_path = (
        ROOT_DIR
        / "results"
        / "season_intelligence"
        / (
            f"{season}_"
            "team_summary_v1.csv"
        )
    )

    history_path = (
        ROOT_DIR
        / "results"
        / "season_intelligence"
        / (
            f"{season}_"
            "team_rating_games_v1.csv"
        )
    )

    if (
        not summary_path.exists()
        or not history_path.exists()
    ):
        raise RuntimeError(
            "Backfill completed without expected "
            "Stage 4 artifacts."
        )

    print()
    print(
        "=" * 72
    )

    print(
        "✓ Historical Season Intelligence backfill complete"
    )

    print(
        "=" * 72
    )

    print(
        f"Season: {season}"
    )

    print(
        f"Summary: {summary_path}"
    )

    print(
        f"History: {history_path}"
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Backfill frozen Courtvision Season "
            "Intelligence for a historical season."
        )
    )

    parser.add_argument(
        "--season",
        required=True,
    )

    parser.add_argument(
        "--fetch-missing",
        action="store_true",
    )

    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.5,
    )

    return parser.parse_args()


def main():
    args = parse_args()

    backfill_season(
        season=args.season,
        fetch_missing=(
            args.fetch_missing
        ),
        sleep_seconds=(
            args.sleep_seconds
        ),
    )


if __name__ == "__main__":
    main()
