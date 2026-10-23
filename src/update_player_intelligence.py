from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from box_score import fetch_box_score
from live_analysis import (
    analyze_live_game,
    load_live_artifacts,
)
from player_impact import (
    analyze_player_impact_from_game_df,
)
from player_rating import (
    build_player_ratings,
)
from player_rating_dataset import (
    OUTPUT_COLUMNS,
    PLAYER_INTELLIGENCE_DIR,
    build_player_game_rows,
    normalize_game_id,
    validate_player_game_dataset,
)
from season_config import (
    CURRENT_SEASON,
    CURRENT_SEASON_TYPE,
)
from update_live_season import (
    atomic_write_csv,
    fetch_completed_season_games,
)


def player_game_path(
    season,
    output_dir=PLAYER_INTELLIGENCE_DIR,
):
    return (
        Path(output_dir)
        / f"{season}_player_game_v1.csv"
    )


def player_rating_path(
    season,
    output_dir=PLAYER_INTELLIGENCE_DIR,
):
    return (
        Path(output_dir)
        / f"{season}_player_ratings_v1.csv"
    )


def load_existing_player_games(
    season,
    output_dir=PLAYER_INTELLIGENCE_DIR,
):
    path = player_game_path(
        season,
        output_dir=output_dir,
    )

    if not path.exists():
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    dataset = pd.read_csv(
        path,
        dtype={
            "gameId": str,
        },
    )
    dataset["gameId"] = dataset["gameId"].map(
        normalize_game_id
    )
    validate_player_game_dataset(dataset)

    if not dataset["season"].eq(season).all():
        raise ValueError(
            f"Published player-game data does not match {season}."
        )

    return dataset


def build_team_context(
    season,
    game,
):
    home_win = int(game.homeWin)

    return pd.DataFrame(
        [
            {
                "season": season,
                "gameId": normalize_game_id(game.gameId),
                "gameDate": str(game.gameDate),
                "teamTricode": str(game.homeTeam),
                "opponentTricode": str(game.awayTeam),
                "isHome": 1,
                "teamWin": home_win,
            },
            {
                "season": season,
                "gameId": normalize_game_id(game.gameId),
                "gameDate": str(game.gameDate),
                "teamTricode": str(game.awayTeam),
                "opponentTricode": str(game.homeTeam),
                "isHome": 0,
                "teamWin": 1 - home_win,
            },
        ]
    )


def process_completed_game(
    season,
    season_type,
    game,
):
    analysis = analyze_live_game(
        game_id=game.gameId,
        season=season,
        game_date=game.gameDate,
        season_type=season_type,
        assume_final=True,
    )
    model, scaler, device = load_live_artifacts()
    impact = analyze_player_impact_from_game_df(
        analysis["model_timeline"],
        model=model,
        scaler=scaler,
        device=device,
    )
    box_score = fetch_box_score(
        game.gameId
    )

    return build_player_game_rows(
        season=season,
        game_id=game.gameId,
        team_games=build_team_context(
            season,
            game,
        ),
        box_players=box_score["players"],
        wpa_summary=impact["summary"],
    )


def update_player_intelligence(
    season=CURRENT_SEASON,
    season_type=CURRENT_SEASON_TYPE,
    output_dir=PLAYER_INTELLIGENCE_DIR,
    timeout=60,
    max_new_games=None,
    completed_games=None,
    game_processor=process_completed_game,
):
    if max_new_games is not None and max_new_games <= 0:
        raise ValueError("max_new_games must be positive.")

    if completed_games is None:
        completed_games = fetch_completed_season_games(
            season=season,
            season_type=season_type,
            timeout=timeout,
        )

    games = completed_games.copy()
    if games.empty:
        games = games.reindex(columns=["gameId", "gameDate"])
    if not games.empty:
        games["gameId"] = games["gameId"].map(
            normalize_game_id
        )
        games["gameDate"] = pd.to_datetime(
            games["gameDate"],
            errors="raise",
        ).dt.strftime("%Y-%m-%d")
        games = games.sort_values(
            [
                "gameDate",
                "gameId",
            ],
            kind="mergesort",
        ).reset_index(drop=True)

    existing = load_existing_player_games(
        season,
        output_dir=output_dir,
    )
    processed_ids = set(
        existing["gameId"].astype(str)
    )
    pending = games.loc[
        ~games["gameId"].isin(processed_ids)
    ].copy()

    if max_new_games is not None:
        pending = pending.head(max_new_games)

    additions = []
    failures = []

    for game in pending.itertuples(index=False):
        print(
            "Player Intelligence: processing "
            f"{game.gameId} ({game.gameDate})"
        )

        try:
            rows = game_processor(season, season_type, game)
            validate_player_game_dataset(rows)
            if not rows["gameId"].map(normalize_game_id).eq(game.gameId).all():
                raise ValueError("Player rows do not match the requested game.")
            if not rows["season"].eq(season).all():
                raise ValueError("Player rows do not match the requested season.")
            additions.append(
                rows
            )
        except Exception as error:
            failures.append(
                {
                    "gameId": game.gameId,
                    "error": str(error),
                }
            )
            print(f"  skipped: {error}")

    frames = [
        frame
        for frame in [existing, *additions]
        if not frame.empty
    ]
    dataset = (
        pd.concat(
            frames,
            ignore_index=True,
        )
        if frames
        else pd.DataFrame(columns=OUTPUT_COLUMNS)
    )

    if not dataset.empty:
        dataset = dataset.sort_values(
            [
                "gameDate",
                "gameId",
                "teamTricode",
                "personId",
            ],
            kind="mergesort",
        ).reset_index(drop=True)
        validate_player_game_dataset(dataset)
        ratings = build_player_ratings(dataset)
        atomic_write_csv(
            dataset,
            player_game_path(
                season,
                output_dir=output_dir,
            ),
        )
        atomic_write_csv(
            ratings,
            player_rating_path(
                season,
                output_dir=output_dir,
            ),
        )
    else:
        ratings = pd.DataFrame()

    print("Player Intelligence update")
    print(f"season: {season}")
    print(f"completed games discovered: {len(games)}")
    print(f"previously published: {len(processed_ids)}")
    print(f"new games published: {len(additions)}")
    print(f"failures retained for retry: {len(failures)}")

    return {
        "games": games,
        "pending": pending,
        "dataset": dataset,
        "ratings": ratings,
        "failures": failures,
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Incrementally publish current-season Player Intelligence."
        )
    )
    parser.add_argument(
        "--season",
        default=CURRENT_SEASON,
    )
    parser.add_argument(
        "--season-type",
        default=CURRENT_SEASON_TYPE,
        choices=[
            "Regular Season",
            "Pre Season",
        ],
    )
    parser.add_argument(
        "--output-dir",
        default=str(PLAYER_INTELLIGENCE_DIR),
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
    )
    parser.add_argument(
        "--max-new-games",
        type=int,
    )
    return parser.parse_args()


def main():
    args = parse_args()
    update_player_intelligence(
        season=args.season,
        season_type=args.season_type,
        output_dir=Path(args.output_dir),
        timeout=args.timeout,
        max_new_games=args.max_new_games,
    )


if __name__ == "__main__":
    main()
