from __future__ import annotations

import argparse
import os
import time
import traceback
from pathlib import Path

import pandas as pd

from nba_api.stats.endpoints import (
    leaguegamefinder,
    playbyplayv3,
)
from nba_api.stats.library.parameters import SeasonType

from preprocess import preprocess_game


ROOT_DIR = (
    Path(__file__)
    .resolve()
    .parents[1]
)

RAW_DIR = (
    ROOT_DIR
    / "data"
    / "raw"
)

PROCESSED_DIR = (
    ROOT_DIR
    / "data"
    / "processed"
)

TRAINING_DIR = (
    ROOT_DIR
    / "data"
    / "training"
)


def get_season_games(
    season,
):
    print(
        f"Fetching regular-season game catalog for {season}..."
    )

    gamefinder = (
        leaguegamefinder.LeagueGameFinder(
            season_nullable=season,
            season_type_nullable=(
                SeasonType.regular
            ),
            player_or_team_abbreviation="T",
            timeout=60,
        )
    )

    games = (
        gamefinder
        .get_data_frames()[
            0
        ]
    )

    game_metadata = (
        games[
            [
                "GAME_ID",
                "GAME_DATE",
            ]
        ]
        .drop_duplicates(
            subset="GAME_ID"
        )
        .rename(
            columns={
                "GAME_ID":
                    "gameId",

                "GAME_DATE":
                    "gameDate",
            }
        )
        .sort_values(
            [
                "gameDate",
                "gameId",
            ],
            kind="mergesort",
        )
        .reset_index(
            drop=True
        )
    )

    game_metadata[
        "gameId"
    ] = (
        game_metadata[
            "gameId"
        ]
        .astype(
            str
        )
        .str.zfill(
            10
        )
    )

    print(
        f"Catalog games: {len(game_metadata):,}"
    )

    return game_metadata


def fetch_game(
    game_id,
    retries=3,
):
    game_id = (
        str(
            game_id
        )
        .zfill(
            10
        )
    )

    raw_path = (
        RAW_DIR
        / f"{game_id}.csv"
    )

    if raw_path.exists():
        return pd.read_csv(
            raw_path
        )

    RAW_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    last_error = None

    for attempt in range(
        1,
        retries + 1,
    ):
        try:
            print(
                f"{game_id}: downloading "
                f"(attempt {attempt}/{retries})"
            )

            endpoint = (
                playbyplayv3.PlayByPlayV3(
                    game_id=game_id,
                    timeout=60,
                )
            )

            df = (
                endpoint
                .get_data_frames()[
                    0
                ]
            )

            df.to_csv(
                raw_path,
                index=False,
            )

            return df

        except Exception as error:
            last_error = error

            print(
                f"{game_id}: download failed: "
                f"{error}"
            )

            if attempt < retries:
                wait_seconds = (
                    3
                    * attempt
                )

                print(
                    f"Retrying in "
                    f"{wait_seconds}s..."
                )

                time.sleep(
                    wait_seconds
                )

    raise RuntimeError(
        f"Could not download {game_id}"
    ) from last_error


def process_game(
    game_id,
):
    game_id = (
        str(
            game_id
        )
        .zfill(
            10
        )
    )

    processed_path = (
        PROCESSED_DIR
        / f"{game_id}.csv"
    )

    if processed_path.exists():
        return pd.read_csv(
            processed_path
        )

    raw_df = fetch_game(
        game_id
    )

    processed_df = (
        preprocess_game(
            raw_df
        )
    )

    PROCESSED_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    processed_df.to_csv(
        processed_path,
        index=False,
    )

    return processed_df


def build_season_dataset(
    season,
    sleep_seconds=0.5,
):
    games = get_season_games(
        season
    )

    all_games = []

    failed_games = []

    total_games = len(
        games
    )

    for index, row in (
        games.iterrows()
    ):
        game_id = str(
            row[
                "gameId"
            ]
        ).zfill(
            10
        )

        game_date = row[
            "gameDate"
        ]

        print(
            f"[{index + 1:,}/{total_games:,}] "
            f"{game_id}"
        )

        try:
            game_df = (
                process_game(
                    game_id
                )
            )

            game_df[
                "gameId"
            ] = game_id

            game_df[
                "gameDate"
            ] = game_date

            all_games.append(
                game_df
            )

        except Exception as error:
            failed_games.append(
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

            print(
                f"FAILED {game_id}: "
                f"{error}"
            )

            traceback.print_exc()

        if (
            sleep_seconds > 0
        ):
            time.sleep(
                sleep_seconds
            )

    if not all_games:
        raise RuntimeError(
            "No games were successfully processed."
        )

    season_df = pd.concat(
        all_games,
        ignore_index=True,
    )

    expected_games = (
        games[
            "gameId"
        ]
        .nunique()
    )

    actual_games = (
        season_df[
            "gameId"
        ]
        .astype(
            str
        )
        .str.zfill(
            10
        )
        .nunique()
    )

    print()
    print(
        f"Expected games: {expected_games:,}"
    )

    print(
        f"Processed games: {actual_games:,}"
    )

    if failed_games:
        failure_path = (
            TRAINING_DIR
            / (
                f"{season}_"
                "fetch_failures.csv"
            )
        )

        TRAINING_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        pd.DataFrame(
            failed_games
        ).to_csv(
            failure_path,
            index=False,
        )

        print(
            f"Failures: {len(failed_games):,}"
        )

        print(
            f"Failure log: {failure_path}"
        )

    if (
        actual_games
        != expected_games
    ):
        raise RuntimeError(
            "Historical season is incomplete: "
            f"{actual_games:,}/{expected_games:,} "
            "games processed."
        )

    return season_df


def create_training_dataset(
    df,
):
    columns = [
        "gameId",
        "gameDate",
        "homeTeamId",
        "awayTeamId",
        "elapsedGameTime",
        "scoreHome",
        "scoreAway",
        "homeScoreDiff",
        "homePossession",
        "homeWin",
    ]

    missing = [
        column
        for column in columns
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            "Processed season data is missing columns: "
            f"{missing}"
        )

    training_df = (
        df[
            columns
        ]
        .copy()
    )

    training_df[
        "gameId"
    ] = (
        training_df[
            "gameId"
        ]
        .astype(
            str
        )
        .str.zfill(
            10
        )
    )

    training_df = (
        training_df
        .dropna(
            subset=[
                "homePossession",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    return training_df


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Fetch and preprocess an NBA regular season "
            "into Courtvision's V4 base training format."
        )
    )

    parser.add_argument(
        "--season",
        required=True,
        help=(
            "NBA season such as 2023-24."
        ),
    )

    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.5,
        help=(
            "Delay between games. Existing local games "
            "are reused automatically."
        ),
    )

    return parser.parse_args()


def main():
    args = parse_args()

    season = args.season

    output_path = (
        TRAINING_DIR
        / (
            f"{season}_"
            "training_v4_base.csv"
        )
    )

    if output_path.exists():
        existing = pd.read_csv(
            output_path,
            dtype={
                "gameId":
                    str,
            },
        )

        print(
            f"Training dataset already exists: "
            f"{output_path}"
        )

        print(
            "Games:",
            existing[
                "gameId"
            ].nunique(),
        )

        print(
            "Rows:",
            len(
                existing
            ),
        )

        return

    season_df = (
        build_season_dataset(
            season=season,
            sleep_seconds=(
                args.sleep_seconds
            ),
        )
    )

    training_df = (
        create_training_dataset(
            season_df
        )
    )

    TRAINING_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    training_df.to_csv(
        output_path,
        index=False,
    )

    print()
    print(
        "✓ Historical base dataset complete."
    )

    print(
        f"Season: {season}"
    )

    print(
        f"Output: {output_path}"
    )

    print(
        "Games:",
        training_df[
            "gameId"
        ].nunique(),
    )

    print(
        "Rows:",
        len(
            training_df
        ),
    )

    print(
        "Columns:",
        training_df.columns.tolist(),
    )


if __name__ == "__main__":
    main()
