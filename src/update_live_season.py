from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd

from nba_api.stats.endpoints import leaguegamefinder

from incremental_team_rating import (
    DEFAULT_RUNTIME_ROOT,
    normalize_game_id,
    run_incremental_update,
)

from team_season_intelligence import (
    SEASON_INTELLIGENCE_DIR,
    build_team_game_history,
    build_team_summary,
    validate_team_summary,
)


ROOT_DIR = (
    Path(__file__)
    .resolve()
    .parents[1]
)


# ============================================================
# Atomic publishing
# ============================================================

def atomic_write_csv(
    df,
    path,
):
    path = Path(
        path
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path = (
        path.parent
        / (
            path.name
            + ".tmp"
        )
    )

    df.to_csv(
        temp_path,
        index=False,
    )

    os.replace(
        temp_path,
        path,
    )


# ============================================================
# NBA completed-game discovery
# ============================================================

def fetch_completed_season_games(
    season,
    season_type="Regular Season",
    timeout=60,
):
    """
    Fetch completed NBA regular-season games and convert the
    two team-level LeagueGameFinder rows into one canonical
    Courtvision row per game.

    This does not fetch play-by-play and does not run V7.
    Frozen Team Courtvision Rating v1 is margin-only.
    """

    endpoint = (
        leaguegamefinder
        .LeagueGameFinder(
            season_nullable=season,
            season_type_nullable=(
                season_type
            ),
            player_or_team_abbreviation="T",
            timeout=timeout,
        )
    )

    raw = (
        endpoint
        .get_data_frames()[0]
        .copy()
    )

    if raw.empty:
        return pd.DataFrame(
            columns=[
                "season",
                "gameDate",
                "gameId",
                "homeTeam",
                "awayTeam",
                "homeWin",
                "winner",
                "winnerMargin",
                "winnerAvgWinProbability",
            ]
        )

    required = [
        "GAME_ID",
        "GAME_DATE",
        "TEAM_ABBREVIATION",
        "MATCHUP",
        "WL",
        "PTS",
    ]

    missing = [
        column
        for column in required
        if column not in raw.columns
    ]

    if missing:
        raise ValueError(
            "LeagueGameFinder response is missing "
            f"required columns: {missing}"
        )

    # A completed game has a known W/L and numeric points.
    raw["PTS"] = pd.to_numeric(
        raw["PTS"],
        errors="coerce",
    )

    raw = raw.loc[
        raw["WL"].isin(
            [
                "W",
                "L",
            ]
        )
        & raw["PTS"].notna()
    ].copy()

    if raw.empty:
        return pd.DataFrame(
            columns=[
                "season",
                "gameDate",
                "gameId",
                "homeTeam",
                "awayTeam",
                "homeWin",
                "winner",
                "winnerMargin",
                "winnerAvgWinProbability",
            ]
        )

    rows = []

    for game_id, game in (
        raw.groupby(
            "GAME_ID",
            sort=False,
        )
    ):
        game = (
            game
            .drop_duplicates(
                subset=[
                    "TEAM_ABBREVIATION",
                ]
            )
            .copy()
        )

        if len(
            game
        ) != 2:
            raise ValueError(
                f"Game {game_id} has "
                f"{len(game)} team rows; expected 2."
            )

        # MATCHUP is game-level metadata. NBA LeagueGameFinder
        # may return the same matchup string on both team rows,
        # so do not infer home/away from the row itself.
        #
        # Examples:
        #   "ORL @ MEM"   -> away=ORL, home=MEM
        #   "MEM vs. ORL" -> home=MEM, away=ORL

        matchup_values = (
            game[
                "MATCHUP"
            ]
            .dropna()
            .astype(
                str
            )
            .str.strip()
            .unique()
            .tolist()
        )

        parsed_matchups = []

        for matchup in matchup_values:
            if " @ " in matchup:
                away_name, home_name = (
                    matchup.split(
                        " @ ",
                        1,
                    )
                )

            elif " vs. " in matchup:
                home_name, away_name = (
                    matchup.split(
                        " vs. ",
                        1,
                    )
                )

            else:
                continue

            parsed_matchups.append(
                (
                    away_name.strip(),
                    home_name.strip(),
                )
            )

        parsed_matchups = list(
            dict.fromkeys(
                parsed_matchups
            )
        )

        if len(
            parsed_matchups
        ) != 1:
            raise ValueError(
                f"Could not uniquely resolve matchup "
                f"for game {game_id}: "
                f"{matchup_values}"
            )

        (
            away_team_name,
            home_team_name,
        ) = parsed_matchups[0]

        home_rows = (
            game.loc[
                game[
                    "TEAM_ABBREVIATION"
                ].astype(
                    str
                )
                == home_team_name
            ]
        )

        away_rows = (
            game.loc[
                game[
                    "TEAM_ABBREVIATION"
                ].astype(
                    str
                )
                == away_team_name
            ]
        )

        if (
            len(
                home_rows
            )
            != 1
            or len(
                away_rows
            )
            != 1
        ):
            raise ValueError(
                f"Could not match resolved teams "
                f"for game {game_id}: "
                f"away={away_team_name}, "
                f"home={home_team_name}"
            )

        home = (
            home_rows.iloc[
                0
            ]
        )

        away = (
            away_rows.iloc[
                0
            ]
        )

        home_team = str(
            home[
                "TEAM_ABBREVIATION"
            ]
        )

        away_team = str(
            away[
                "TEAM_ABBREVIATION"
            ]
        )

        home_points = int(
            home[
                "PTS"
            ]
        )

        away_points = int(
            away[
                "PTS"
            ]
        )

        if (
            home_points
            == away_points
        ):
            raise ValueError(
                f"Completed game {game_id} "
                "has a tied final score."
            )

        home_win = int(
            home_points
            > away_points
        )

        winner = (
            home_team
            if home_win == 1
            else away_team
        )

        winner_margin = abs(
            home_points
            - away_points
        )

        game_dates = (
            game[
                "GAME_DATE"
            ]
            .dropna()
            .astype(
                str
            )
            .unique()
            .tolist()
        )

        if len(
            game_dates
        ) != 1:
            raise ValueError(
                f"Game {game_id} has inconsistent "
                f"GAME_DATE values: {game_dates}"
            )

        rows.append(
            {
                "season":
                    str(
                        season
                    ),

                "gameDate":
                    game_dates[
                        0
                    ],

                "gameId":
                    normalize_game_id(
                        game_id
                    ),

                "homeTeam":
                    home_team,

                "awayTeam":
                    away_team,

                "homeWin":
                    home_win,

                "winner":
                    winner,

                "winnerMargin":
                    winner_margin,

                # Required by the historical canonical schema.
                #
                # Frozen Team Courtvision Rating v1 uses
                # FROZEN_MARGIN_WEIGHT = 1.0, so WP control has
                # zero numerical weight in the rating update.
                "winnerAvgWinProbability":
                    0.5,
            }
        )

    games = pd.DataFrame(
        rows
    )

    games[
        "_sortDate"
    ] = pd.to_datetime(
        games[
            "gameDate"
        ],
        errors="coerce",
    )

    if games[
        "_sortDate"
    ].isna().any():
        raise ValueError(
            "Invalid GAME_DATE returned by NBA API."
        )

    games = (
        games
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

    if games[
        "gameId"
    ].duplicated().any():
        raise ValueError(
            "Completed-game discovery produced "
            "duplicate game IDs."
        )

    return games


# ============================================================
# Runtime inspection
# ============================================================

def load_processed_game_ids(
    season,
    runtime_root,
):
    history_path = (
        Path(
            runtime_root
        )
        / season
        / "rating_history_v1.csv"
    )

    if not history_path.exists():
        return set()

    history = pd.read_csv(
        history_path,
        dtype={
            "gameId":
                str,
        },
    )

    if (
        history.empty
        or "gameId"
        not in history.columns
    ):
        return set()

    return set(
        history[
            "gameId"
        ]
        .map(
            normalize_game_id
        )
        .tolist()
    )


# ============================================================
# Dashboard publishing
# ============================================================

def publish_season_intelligence(
    season,
    history,
    ratings,
    output_dir=SEASON_INTELLIGENCE_DIR,
):
    if history.empty:
        raise ValueError(
            "Cannot publish Season Intelligence "
            "without completed games."
        )

    team_history = (
        build_team_game_history(
            history
        )
    )

    summary = (
        build_team_summary(
            team_history,
            ratings,
        )
    )

    validate_team_summary(
        summary,
        team_history,
        ratings,
    )

    output_dir = Path(
        output_dir
    )

    summary_path = (
        output_dir
        / (
            f"{season}_"
            "team_summary_v1.csv"
        )
    )

    team_history_path = (
        output_dir
        / (
            f"{season}_"
            "team_rating_games_v1.csv"
        )
    )

    atomic_write_csv(
        summary,
        summary_path,
    )

    atomic_write_csv(
        team_history,
        team_history_path,
    )

    return (
        summary,
        summary_path,
        team_history_path,
    )


# ============================================================
# Update orchestration
# ============================================================

def update_live_season(
    season,
    runtime_root=DEFAULT_RUNTIME_ROOT,
    timeout=60,
    dry_run=False,
    publish=True,
    publish_dir=SEASON_INTELLIGENCE_DIR,
    season_type="Regular Season",
):
    runtime_root = Path(
        runtime_root
    )

    if (
        season_type == "Pre Season"
        and runtime_root.resolve()
        == Path(
            DEFAULT_RUNTIME_ROOT
        ).resolve()
        and not dry_run
    ):
        raise ValueError(
            "Refusing to write preseason games into the "
            "production Team Courtvision Rating runtime. "
            "Use a separate --runtime-root for preseason testing."
        )

    games = (
        fetch_completed_season_games(
            season=season,
            season_type=season_type,
            timeout=timeout,
        )
    )

    processed = (
        load_processed_game_ids(
            season=season,
            runtime_root=runtime_root,
        )
    )

    discovered_ids = set(
        games[
            "gameId"
        ].tolist()
    )

    new_ids = (
        discovered_ids
        - processed
    )

    pending = (
        games.loc[
            games[
                "gameId"
            ].isin(
                new_ids
            )
        ]
        .copy()
    )

    print()
    print(
        "Courtvision Live Season Adapter"
    )

    print(
        f"Season: {season}"
    )

    print(
        f"Season type: {season_type}"
    )

    print(
        "Completed games discovered: "
        f"{len(games):,}"
    )

    print(
        "Already processed: "
        f"{len(discovered_ids & processed):,}"
    )

    print(
        "New completed games: "
        f"{len(pending):,}"
    )

    if not pending.empty:
        print()

        print(
            pending[
                [
                    "gameDate",
                    "gameId",
                    "awayTeam",
                    "homeTeam",
                    "winner",
                    "winnerMargin",
                ]
            ]
            .to_string(
                index=False
            )
        )

    if dry_run:
        print()
        print(
            "Dry run: no files were changed."
        )

        return {
            "games":
                games,

            "pending":
                pending,

            "history":
                None,

            "ratings":
                None,

            "summary":
                None,
        }

    if games.empty:
        print()
        print(
            "No completed games are available yet."
        )

        print(
            "No runtime or dashboard artifacts were changed."
        )

        return {
            "games":
                games,

            "pending":
                pending,

            "history":
                None,

            "ratings":
                None,

            "summary":
                None,
        }

    history, ratings, runtime_paths = (
        run_incremental_update(
            season=season,
            games=games,
            runtime_root=(
                runtime_root
            ),
        )
    )

    summary = None
    summary_path = None
    team_history_path = None

    if (
        publish
        and not history.empty
    ):
        (
            summary,
            summary_path,
            team_history_path,
        ) = (
            publish_season_intelligence(
                season=season,
                history=history,
                ratings=ratings,
                output_dir=publish_dir,
            )
        )

        print()
        print(
            "Published dashboard artifacts:"
        )

        print(
            f"  {summary_path}"
        )

        print(
            f"  {team_history_path}"
        )

    print()
    print(
        "Runtime artifacts:"
    )

    for name, path in (
        runtime_paths.items()
    ):
        print(
            f"  {name}: {path}"
        )

    return {
        "games":
            games,

        "pending":
            pending,

        "history":
            history,

        "ratings":
            ratings,

        "summary":
            summary,
    }


# ============================================================
# CLI
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Discover completed NBA regular-season games, "
            "incrementally update frozen Team Courtvision "
            "Rating v1, and publish Season Intelligence."
        )
    )

    parser.add_argument(
        "--season",
        required=True,
        help=(
            "NBA season, for example 2026-27."
        ),
    )

    parser.add_argument(
        "--runtime-root",
        default=str(
            DEFAULT_RUNTIME_ROOT
        ),
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
    )

    parser.add_argument(
        "--season-type",
        choices=[
            "Regular Season",
            "Pre Season",
        ],
        default="Regular Season",
        help=(
            "NBA season type to discover. "
            "Regular Season is the production default."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Discover and report pending games without "
            "changing runtime or dashboard artifacts."
        ),
    )

    parser.add_argument(
        "--no-publish",
        action="store_true",
        help=(
            "Update incremental rating state without "
            "publishing dashboard Season Intelligence."
        ),
    )

    parser.add_argument(
        "--publish-dir",
        default=str(
            SEASON_INTELLIGENCE_DIR
        ),
        help=(
            "Directory for dashboard-facing Season "
            "Intelligence artifacts."
        ),
    )

    return parser.parse_args()


def main():
    args = parse_args()

    update_live_season(
        season=args.season,
        runtime_root=Path(
            args.runtime_root
        ),
        timeout=args.timeout,
        dry_run=args.dry_run,
        publish=(
            not args.no_publish
        ),
        publish_dir=Path(
            args.publish_dir
        ),
        season_type=(
            args.season_type
        ),
    )


if __name__ == "__main__":
    main()
