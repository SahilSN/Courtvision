import argparse
import time
import traceback
from pathlib import Path

import pandas as pd

from nba_api.stats.endpoints import (
    leaguegamelog,
    playbyplayv3,
)

from preprocess import (
    preprocess_game,
)


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
    timeout=60,
):
    endpoint = (
        leaguegamelog
        .LeagueGameLog(
            season=season,
            season_type_all_star=(
                "Regular Season"
            ),
            player_or_team_abbreviation=(
                "T"
            ),
            timeout=timeout,
        )
    )

    df = (
        endpoint
        .get_data_frames()[0]
        .copy()
    )

    games = (
        df[
            [
                "GAME_ID",
                "GAME_DATE",
            ]
        ]
        .drop_duplicates(
            subset=[
                "GAME_ID"
            ]
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
            ]
        )
        .reset_index(
            drop=True
        )
    )

    return games


def fetch_raw_game(
    game_id,
    timeout=60,
):
    canonical_game_id = (
        str(
            game_id
        )
        .zfill(10)
    )

    RAW_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = (
        RAW_DIR
        / (
            f"{canonical_game_id}"
            ".csv"
        )
    )

    if path.exists():
        print(
            f"{canonical_game_id}: "
            "raw cached"
        )

        return pd.read_csv(
            path
        )

    print(
        f"{canonical_game_id}: "
        "downloading"
    )

    endpoint = (
        playbyplayv3
        .PlayByPlayV3(
            game_id=(
                canonical_game_id
            ),
            timeout=timeout,
        )
    )

    df = (
        endpoint
        .get_data_frames()[0]
        .copy()
    )

    df.to_csv(
        path,
        index=False,
    )

    return df


def process_game(
    game_id,
):
    canonical_game_id = (
        str(
            game_id
        )
        .zfill(10)
    )

    PROCESSED_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = (
        PROCESSED_DIR
        / (
            f"{canonical_game_id}"
            ".csv"
        )
    )

    if path.exists():
        print(
            f"{canonical_game_id}: "
            "processed cached"
        )

        return pd.read_csv(
            path
        )

    raw_df = (
        fetch_raw_game(
            canonical_game_id
        )
    )

    processed_df = (
        preprocess_game(
            raw_df
        )
    )

    processed_df.to_csv(
        path,
        index=False,
    )

    return processed_df


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

    training_df = (
        df[
            columns
        ]
        .copy()
        .dropna(
            subset=[
                "homePossession"
            ]
        )
        .reset_index(
            drop=True
        )
    )

    training_df[
        "gameId"
    ] = (
        training_df[
            "gameId"
        ]
        .astype(str)
        .str.lstrip("0")
        .astype(int)
    )

    return training_df


def build_season_dataset(
    season,
    sleep_seconds=1.0,
    max_games=None,
):
    games = (
        get_season_games(
            season
        )
    )

    if (
        max_games
        is not None
    ):
        games = (
            games.iloc[
                :max_games
            ]
            .copy()
        )

    all_games = []

    failures = []

    for position, (
        _,
        game,
    ) in enumerate(
        games.iterrows(),
        start=1,
    ):
        game_id = (
            game[
                "gameId"
            ]
        )

        game_date = (
            game[
                "gameDate"
            ]
        )

        print(
            f"[{position}/"
            f"{len(games)}] "
            f"{game_id}"
        )

        try:
            game_df = (
                process_game(
                    game_id
                )
            )

            game_df[
                "gameDate"
            ] = (
                game_date
            )

            all_games.append(
                game_df
            )

        except Exception as error:
            failures.append(
                {
                    "gameId":
                        game_id,

                    "error":
                        str(
                            error
                        ),
                }
            )

            print(
                f"FAILED "
                f"{game_id}: "
                f"{error}"
            )

            traceback.print_exc()

        time.sleep(
            sleep_seconds
        )

    if not all_games:
        raise RuntimeError(
            "No games were "
            "successfully processed."
        )

    combined = pd.concat(
        all_games,
        ignore_index=True,
    )

    return (
        combined,
        failures,
    )


def main():
    parser = (
        argparse.ArgumentParser()
    )

    parser.add_argument(
        "--season",
        required=True,
    )

    parser.add_argument(
        "--sleep",
        type=float,
        default=1.0,
    )

    parser.add_argument(
        "--max-games",
        type=int,
        default=None,
    )

    parser.add_argument(
        "--output-suffix",
        default="",
        help=(
            "Useful for pilot files, "
            "e.g. _pilot."
        ),
    )

    args = (
        parser.parse_args()
    )

    (
        season_df,
        failures,
    ) = (
        build_season_dataset(
            season=(
                args.season
            ),
            sleep_seconds=(
                args.sleep
            ),
            max_games=(
                args.max_games
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

    output_path = (
        TRAINING_DIR
        / (
            f"{args.season}"
            "_training_v4_base"
            f"{args.output_suffix}"
            ".csv"
        )
    )

    training_df.to_csv(
        output_path,
        index=False,
    )

    print()
    print(
        "Saved:",
        output_path,
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
        "Failures:",
        len(
            failures
        ),
    )

    if failures:
        failure_path = (
            TRAINING_DIR
            / (
                f"{args.season}"
                "_fetch_failures.csv"
            )
        )

        pd.DataFrame(
            failures
        ).to_csv(
            failure_path,
            index=False,
        )

        print(
            "Failure log:",
            failure_path,
        )


if __name__ == "__main__":
    main()