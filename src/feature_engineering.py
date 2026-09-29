import pandas as pd


MODEL_FEATURES = [
    "elapsedGameTime",
    "homeScoreDiff",
    "homePossession",
    "totalScore",
    "homePreGameWinPct",
    "awayPreGameWinPct",
    "strengthDifference",
    "scoreDiffLateWeight",
]


def add_pregame_strength(df):
    df = df.copy()

    games = (
        df[
            [
                "gameId",
                "gameDate",
                "homeTeamId",
                "awayTeamId",
                "homeWin",
            ]
        ]
        .drop_duplicates(
            subset="gameId"
        )
        .copy()
    )

    games["gameDate"] = (
        pd.to_datetime(
            games["gameDate"]
        )
    )

    games = (
        games
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

    team_wins = {}
    team_games = {}

    strength_rows = []

    for _, game in (
        games.iterrows()
    ):
        home_team = int(
            game[
                "homeTeamId"
            ]
        )

        away_team = int(
            game[
                "awayTeamId"
            ]
        )

        home_games_played = (
            team_games.get(
                home_team,
                0,
            )
        )

        away_games_played = (
            team_games.get(
                away_team,
                0,
            )
        )

        home_wins = (
            team_wins.get(
                home_team,
                0,
            )
        )

        away_wins = (
            team_wins.get(
                away_team,
                0,
            )
        )

        home_losses = (
            home_games_played
            - home_wins
        )

        away_losses = (
            away_games_played
            - away_wins
        )

        if (
            home_games_played
            == 0
        ):
            home_win_pct = (
                0.5
            )

        else:
            home_win_pct = (
                home_wins
                / home_games_played
            )

        if (
            away_games_played
            == 0
        ):
            away_win_pct = (
                0.5
            )

        else:
            away_win_pct = (
                away_wins
                / away_games_played
            )

        strength_rows.append(
            {
                "gameId":
                    game[
                        "gameId"
                    ],

                "homePreGameWins":
                    home_wins,

                "homePreGameLosses":
                    home_losses,

                "awayPreGameWins":
                    away_wins,

                "awayPreGameLosses":
                    away_losses,

                "homePreGameWinPct":
                    home_win_pct,

                "awayPreGameWinPct":
                    away_win_pct,

                "strengthDifference":
                    (
                        home_win_pct
                        -
                        away_win_pct
                    ),
            }
        )

        home_win = int(
            game["homeWin"]
        )

        away_win = (
            1 - home_win
        )

        team_games[
            home_team
        ] = (
            home_games_played
            + 1
        )

        team_games[
            away_team
        ] = (
            away_games_played
            + 1
        )

        team_wins[
            home_team
        ] = (
            home_wins
            + home_win
        )

        team_wins[
            away_team
        ] = (
            away_wins
            + away_win
        )

    strength_df = (
        pd.DataFrame(
            strength_rows
        )
    )

    df = df.merge(
        strength_df,
        on="gameId",
        how="left",
        validate="many_to_one",
    )

    return df


def add_score_time_features(
    df,
):
    df = df.copy()

    df["totalScore"] = (
        df["scoreHome"]
        + df["scoreAway"]
    )

    regulation_progress = (
        df[
            "elapsedGameTime"
        ]
        / 2880.0
    ).clip(
        lower=0.0,
        upper=1.0,
    )

    df[
        "scoreDiffLateWeight"
    ] = (
        df[
            "homeScoreDiff"
        ]
        * regulation_progress
    )

    return df


def add_model_features(df):
    df = (
        add_score_time_features(
            df
        )
    )

    df = (
        add_pregame_strength(
            df
        )
    )

    return df


def get_pregame_context(
    season_df,
    game_id,
):
    """
    Recreate the exact leakage-safe
    pregame context for one game
    from a complete local season file.
    """

    feature_df = (
        add_pregame_strength(
            season_df
        )
    )

    game_id = int(
        str(game_id)
    )

    game_df = feature_df[
        feature_df[
            "gameId"
        ].astype(int)
        == game_id
    ]

    if game_df.empty:
        raise ValueError(
            f"Game {game_id} "
            "not found in season data."
        )

    row = (
        game_df.iloc[0]
    )

    return {
        "homeTeamId":
            int(
                row[
                    "homeTeamId"
                ]
            ),

        "awayTeamId":
            int(
                row[
                    "awayTeamId"
                ]
            ),

        "homePreGameWins":
            int(
                row[
                    "homePreGameWins"
                ]
            ),

        "homePreGameLosses":
            int(
                row[
                    "homePreGameLosses"
                ]
            ),

        "awayPreGameWins":
            int(
                row[
                    "awayPreGameWins"
                ]
            ),

        "awayPreGameLosses":
            int(
                row[
                    "awayPreGameLosses"
                ]
            ),

        "homePreGameWinPct":
            float(
                row[
                    "homePreGameWinPct"
                ]
            ),

        "awayPreGameWinPct":
            float(
                row[
                    "awayPreGameWinPct"
                ]
            ),

        "strengthDifference":
            float(
                row[
                    "strengthDifference"
                ]
            ),
    }


def add_live_model_features(
    game_df,
    pregame_context,
):
    """
    Add the exact V7 inputs to a
    partial/live game without requiring
    the final outcome.
    """

    df = (
        add_score_time_features(
            game_df
        )
    )

    df[
        "homePreGameWinPct"
    ] = float(
        pregame_context[
            "homePreGameWinPct"
        ]
    )

    df[
        "awayPreGameWinPct"
    ] = float(
        pregame_context[
            "awayPreGameWinPct"
        ]
    )

    df[
        "strengthDifference"
    ] = float(
        pregame_context[
            "strengthDifference"
        ]
    )

    return df