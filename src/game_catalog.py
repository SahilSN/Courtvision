from datetime import date
from pathlib import Path
import time

import pandas as pd

from nba_api.stats.endpoints import (
    leaguegamelog,
    scoreboardv3,
)



ROOT_DIR = (
    Path(__file__)
    .resolve()
    .parents[1]
)

BUNDLED_GAME_CATALOG_DIR = (
    ROOT_DIR
    / "data"
    / "game_catalog"
)

GAME_CATALOG_CACHE_DIR = (
    ROOT_DIR
    / "data"
    / "cache"
    / "game_catalog"
)

GAME_CATALOG_CACHE_TTL_SECONDS = (
    6 * 60 * 60
)


def _format_date(
    game_date,
):
    timestamp = pd.Timestamp(
        game_date
    )

    return timestamp.strftime(
        "%m/%d/%Y"
    )


def fetch_season_games(
    season,
    season_type="Regular Season",
    timeout=60,
    force_refresh=False,
):
    """
    Fetch all team-level LeagueGameLog rows for one season.

    Results are persisted to disk so restarting Streamlit does
    not require another NBA API request. The current cache
    expires after six hours; force_refresh bypasses it.
    """

    safe_season_type = (
        str(season_type)
        .lower()
        .replace(" ", "_")
    )

    catalog_filename = (
        f"leaguegamelog_{season}_"
        f"{safe_season_type}.csv"
    )

    bundled_path = (
        BUNDLED_GAME_CATALOG_DIR
        / catalog_filename
    )

    cache_path = (
        GAME_CATALOG_CACHE_DIR
        / catalog_filename
    )

    if (
        bundled_path.exists()
        and not force_refresh
    ):
        return pd.read_csv(
            bundled_path,
            dtype={
                "GAME_ID": str,
            },
        )

    if (
        cache_path.exists()
        and not force_refresh
    ):
        age_seconds = (
            time.time()
            - cache_path.stat().st_mtime
        )

        if (
            age_seconds
            <= GAME_CATALOG_CACHE_TTL_SECONDS
        ):
            try:
                return pd.read_csv(
                    cache_path,
                    dtype={
                        "GAME_ID": str,
                    },
                )

            except Exception:
                pass

    endpoint = (
        leaguegamelog
        .LeagueGameLog(
            season=season,
            season_type_all_star=(
                season_type
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

    GAME_CATALOG_CACHE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        df.to_csv(
            cache_path,
            index=False,
        )

    except Exception:
        # A cache write failure should never prevent the
        # dashboard from using a successful API response.
        pass

    return df



def fetch_game_statuses_for_date(
    game_date,
    timeout=60,
):
    """
    Return authoritative NBA lifecycle status keyed by game ID.

    This is intentionally separate from the season game catalog.
    LeagueGameLog remains the matchup source; ScoreboardV3 is used
    only for live lifecycle semantics such as Final / Final/OT.
    """
    formatted_date = (
        pd.Timestamp(
            game_date
        )
        .strftime(
            "%Y-%m-%d"
        )
    )

    scoreboard = (
        scoreboardv3.ScoreboardV3(
            game_date=formatted_date,
            timeout=timeout,
        )
    )

    frames = (
        scoreboard.get_data_frames()
    )

    if len(frames) < 2:
        return {}

    games_df = (
        frames[1].copy()
    )

    if games_df.empty:
        return {}

    statuses = {}

    for _, row in games_df.iterrows():
        game_id = str(
            row["gameId"]
        ).zfill(10)

        raw_status = row.get(
            "gameStatus"
        )

        game_status = (
            None
            if pd.isna(
                raw_status
            )
            else int(
                raw_status
            )
        )

        raw_period = row.get(
            "period"
        )

        period = (
            None
            if pd.isna(
                raw_period
            )
            else int(
                raw_period
            )
        )

        statuses[
            game_id
        ] = {
            "game_status":
                game_status,

            "game_status_text":
                str(
                    row.get(
                        "gameStatusText",
                        "",
                    )
                ).strip(),

            "period":
                period,

            "game_clock":
                str(
                    row.get(
                        "gameClock",
                        "",
                    )
                ).strip(),
        }

    return statuses


def fetch_games_for_date_from_scoreboard(
    game_date,
    timeout=60,
):
    """
    Return scheduled/live/completed NBA games for one date.

    ScoreboardV3 is the authoritative discovery source for
    Courtvision Live mode. The returned records intentionally
    match games_for_date_from_season_df().
    """
    formatted_date = (
        pd.Timestamp(
            game_date
        )
        .strftime(
            "%Y-%m-%d"
        )
    )

    scoreboard = (
        scoreboardv3.ScoreboardV3(
            game_date=formatted_date,
            timeout=timeout,
        )
    )

    frames = (
        scoreboard.get_data_frames()
    )

    if len(frames) < 4:
        return []

    games_df = frames[1].copy()
    teams_df = frames[2].copy()
    leaders_df = frames[3].copy()

    if games_df.empty:
        return []

    games = []

    for _, game_row in games_df.iterrows():
        game_id = str(
            game_row[
                "gameId"
            ]
        ).zfill(
            10
        )

        game_teams = (
            teams_df.loc[
                teams_df[
                    "gameId"
                ].astype(str)
                == str(
                    game_row[
                        "gameId"
                    ]
                )
            ]
            .copy()
        )

        game_leaders = (
            leaders_df.loc[
                leaders_df[
                    "gameId"
                ].astype(str)
                == str(
                    game_row[
                        "gameId"
                    ]
                )
            ]
            .copy()
        )

        home_leaders = (
            game_leaders.loc[
                game_leaders[
                    "leaderType"
                ].astype(str)
                .str.lower()
                == "home"
            ]
        )

        away_leaders = (
            game_leaders.loc[
                game_leaders[
                    "leaderType"
                ].astype(str)
                .str.lower()
                == "away"
            ]
        )

        if (
            home_leaders.empty
            or away_leaders.empty
        ):
            continue

        home_tricode = str(
            home_leaders.iloc[0][
                "teamTricode"
            ]
        ).strip()

        away_tricode = str(
            away_leaders.iloc[0][
                "teamTricode"
            ]
        ).strip()

        home_rows = (
            game_teams.loc[
                game_teams[
                    "teamTricode"
                ].astype(str)
                == home_tricode
            ]
        )

        away_rows = (
            game_teams.loc[
                game_teams[
                    "teamTricode"
                ].astype(str)
                == away_tricode
            ]
        )

        if (
            home_rows.empty
            or away_rows.empty
        ):
            continue

        home = home_rows.iloc[0]
        away = away_rows.iloc[0]

        games.append(
            {
                "game_id":
                    game_id,

                "game_date":
                    formatted_date,

                "home_team_id":
                    int(
                        home[
                            "teamId"
                        ]
                    ),

                "away_team_id":
                    int(
                        away[
                            "teamId"
                        ]
                    ),

                "home_tricode":
                    home_tricode,

                "away_tricode":
                    away_tricode,

                "label":
                    (
                        f"{away_tricode} "
                        f"@ "
                        f"{home_tricode}"
                    ),
            }
        )

    games.sort(
        key=lambda game:
            game[
                "label"
            ]
    )

    return games


def games_for_date_from_season_df(
    season_df,
    game_date,
):
    """
    Filter a preloaded season LeagueGameLog dataframe down to
    one calendar date and return Courtvision matchup records.
    """

    if season_df is None:
        return []

    df = season_df.copy()

    if df.empty:
        return []

    target_date = pd.Timestamp(
        game_date
    ).normalize()

    df[
        "_courtvisionGameDate"
    ] = pd.to_datetime(
        df[
            "GAME_DATE"
        ],
        errors="coerce",
    ).dt.normalize()

    df = (
        df[
            df[
                "_courtvisionGameDate"
            ]
            == target_date
        ]
        .copy()
    )

    if df.empty:
        return []

    games = []

    for (
        game_id,
        group,
    ) in df.groupby(
        "GAME_ID",
        sort=False,
    ):
        home_rows = group[
            group[
                "MATCHUP"
            ].str.contains(
                "vs.",
                regex=False,
                na=False,
            )
        ]

        away_rows = group[
            group[
                "MATCHUP"
            ].str.contains(
                "@",
                regex=False,
                na=False,
            )
        ]

        if (
            home_rows.empty
            or away_rows.empty
        ):
            continue

        home = (
            home_rows.iloc[0]
        )

        away = (
            away_rows.iloc[0]
        )

        home_tricode = str(
            home[
                "TEAM_ABBREVIATION"
            ]
        )

        away_tricode = str(
            away[
                "TEAM_ABBREVIATION"
            ]
        )

        games.append(
            {
                "game_id":
                    str(
                        game_id
                    ),

                "game_date":
                    str(
                        home[
                            "GAME_DATE"
                        ]
                    ),

                "home_team_id":
                    int(
                        home[
                            "TEAM_ID"
                        ]
                    ),

                "away_team_id":
                    int(
                        away[
                            "TEAM_ID"
                        ]
                    ),

                "home_tricode":
                    home_tricode,

                "away_tricode":
                    away_tricode,

                "label":
                    (
                        f"{away_tricode} "
                        f"@ "
                        f"{home_tricode}"
                    ),
            }
        )

    games.sort(
        key=lambda game:
            game[
                "label"
            ]
    )

    return games


def fetch_games_for_date(
    season,
    game_date,
    season_type="Regular Season",
    timeout=60,
):
    """
    Backward-compatible helper.

    Fetches the season log once for this call, then filters
    locally. Streamlit should prefer caching fetch_season_games()
    and calling games_for_date_from_season_df().
    """

    season_df = (
        fetch_season_games(
            season=season,
            season_type=season_type,
            timeout=timeout,
        )
    )

    return (
        games_for_date_from_season_df(
            season_df=season_df,
            game_date=game_date,
        )
    )
