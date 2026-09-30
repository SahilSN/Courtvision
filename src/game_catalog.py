from datetime import date
from pathlib import Path
import time

import pandas as pd

from nba_api.stats.endpoints import (
    leaguegamelog,
)



ROOT_DIR = (
    Path(__file__)
    .resolve()
    .parents[1]
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

    cache_path = (
        GAME_CATALOG_CACHE_DIR
        / (
            f"leaguegamelog_{season}_"
            f"{safe_season_type}.csv"
        )
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
