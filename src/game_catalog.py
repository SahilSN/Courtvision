from datetime import date

import pandas as pd

from nba_api.stats.endpoints import (
    leaguegamelog,
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


def fetch_games_for_date(
    season,
    game_date,
    season_type="Regular Season",
    timeout=60,
):
    """
    Return the regular-season NBA games
    recorded for one calendar date.

    One game appears as two LeagueGameLog
    rows, one per team, so this combines
    them into one matchup.
    """

    if isinstance(
        game_date,
        date,
    ):
        date_string = (
            game_date.strftime(
                "%m/%d/%Y"
            )
        )

    else:
        date_string = (
            _format_date(
                game_date
            )
        )

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
            date_from_nullable=(
                date_string
            ),
            date_to_nullable=(
                date_string
            ),
            timeout=timeout,
        )
    )

    df = (
        endpoint
        .get_data_frames()[0]
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