import re

import pandas as pd


class IncompletePlayByPlayError(ValueError):
    """Live PBP does not yet contain enough usable game state."""


def parse_clock(clock, period_length):
    match = re.fullmatch(
        r"PT(?:(\d+)M)?(\d+(?:\.\d+)?)S",
        str(clock),
    )

    if match is None:
        raise ValueError(
            f"Unexpected clock format: {clock!r}"
        )

    minutes_remaining = int(
        match.group(1) or 0
    )

    seconds_remaining = float(
        match.group(2)
    )

    remaining = (
        minutes_remaining * 60
        + seconds_remaining
    )

    return (
        period_length
        - remaining
    )


def fill_scores(df):
    df = df.copy()

    df["scoreHome"] = pd.to_numeric(
        df["scoreHome"],
        errors="coerce",
    )

    df["scoreAway"] = pd.to_numeric(
        df["scoreAway"],
        errors="coerce",
    )

    df["scoreHome"] = (
        df["scoreHome"]
        .ffill()
        .fillna(0)
        .astype(int)
    )

    df["scoreAway"] = (
        df["scoreAway"]
        .ffill()
        .fillna(0)
        .astype(int)
    )

    df["homeScoreDiff"] = (
        df["scoreHome"]
        - df["scoreAway"]
    )

    return df


def add_elapsed_game_time(df):
    df = df.copy()

    for index, row in df.iterrows():
        period = int(
            row["period"]
        )

        try:
            if 1 <= period <= 4:
                elapsed = (
                    720
                    * (period - 1)
                    + parse_clock(
                        row["clock"],
                        720,
                    )
                )

            else:
                overtime_period = (
                    period - 5
                )

                elapsed = (
                    2880
                    + 300
                    * overtime_period
                    + parse_clock(
                        row["clock"],
                        300,
                    )
                )

            df.at[
                index,
                "elapsedGameTime",
            ] = elapsed

        except Exception as error:
            raise ValueError(
                f"Failed on row {index}: "
                f"period={period}, "
                f"clock={row['clock']!r}"
            ) from error

    return df


def is_final_free_throw(
    sub_type,
):
    if not isinstance(
        sub_type,
        str,
    ):
        return False

    parts = (
        sub_type.split()
    )

    if "of" not in parts:
        return False

    try:
        of_index = (
            parts.index("of")
        )

        attempt = int(
            parts[
                of_index - 1
            ]
        )

        total = int(
            parts[
                of_index + 1
            ]
        )

        return (
            attempt
            == total
        )

    except (
        ValueError,
        IndexError,
    ):
        return False


def get_other_team(
    df,
    team_id,
):
    other_team_rows = df[
        (
            df["teamId"]
            != 0
        )
        &
        (
            df["teamId"]
            != team_id
        )
    ]

    if other_team_rows.empty:
        return None

    other_team = (
        other_team_rows
        .iloc[0]
    )

    return (
        other_team[
            "teamId"
        ],
        other_team[
            "teamTricode"
        ],
    )


def score_changed(
    df,
    index,
):
    if index == 0:
        return False

    current_total = (
        df.at[
            index,
            "scoreHome",
        ]
        +
        df.at[
            index,
            "scoreAway",
        ]
    )

    previous_total = (
        df.at[
            index - 1,
            "scoreHome",
        ]
        +
        df.at[
            index - 1,
            "scoreAway",
        ]
    )

    return (
        current_total
        > previous_total
    )


def add_possession_state(df):
    df = df.copy()

    current_possession = None

    df[
        "possessionTeamId"
    ] = pd.NA

    df[
        "possessionTeamTricode"
    ] = pd.NA

    for index, row in df.iterrows():
        action_type = (
            row["actionType"]
        )

        team_id = (
            row["teamId"]
        )

        team_tricode = (
            row["teamTricode"]
        )

        if (
            current_possession
            is None
            and team_id != 0
            and action_type
            in [
                "Made Shot",
                "Missed Shot",
                "Turnover",
                "Free Throw",
            ]
        ):
            current_possession = (
                team_id,
                team_tricode,
            )

        if (
            action_type
            == "Turnover"
        ):
            other_team = (
                get_other_team(
                    df,
                    team_id,
                )
            )

            if (
                other_team
                is not None
            ):
                current_possession = (
                    other_team
                )

        elif (
            action_type
            == "Made Shot"
        ):
            other_team = (
                get_other_team(
                    df,
                    team_id,
                )
            )

            if (
                other_team
                is not None
            ):
                current_possession = (
                    other_team
                )

        elif (
            action_type
            == "Rebound"
        ):
            if team_id != 0:
                current_possession = (
                    team_id,
                    team_tricode,
                )

        elif (
            action_type
            == "Free Throw"
            and is_final_free_throw(
                row["subType"]
            )
            and score_changed(
                df,
                index,
            )
        ):
            other_team = (
                get_other_team(
                    df,
                    team_id,
                )
            )

            if (
                other_team
                is not None
            ):
                current_possession = (
                    other_team
                )

        if (
            current_possession
            is not None
        ):
            df.at[
                index,
                "possessionTeamId",
            ] = (
                current_possession[
                    0
                ]
            )

            df.at[
                index,
                "possessionTeamTricode",
            ] = (
                current_possession[
                    1
                ]
            )

    return df


def get_team_ids(df):
    previous_home = 0
    previous_away = 0

    home_team_id = None
    away_team_id = None

    for _, row in df.iterrows():
        current_home = (
            row["scoreHome"]
        )

        current_away = (
            row["scoreAway"]
        )

        team_id = (
            row["teamId"]
        )

        if team_id == 0:
            continue

        if (
            current_home
            > previous_home
        ):
            home_team_id = (
                team_id
            )

            break

        if (
            current_away
            > previous_away
        ):
            away_team_id = (
                team_id
            )

            break

        previous_home = (
            current_home
        )

        previous_away = (
            current_away
        )

    team_ids = [
        team_id
        for team_id
        in df[
            "teamId"
        ].unique()
        if team_id != 0
    ]

    if (
        home_team_id
        is not None
    ):
        away_team_id = next(
            (
                team_id
                for team_id
                in team_ids
                if team_id
                != home_team_id
            ),
            None,
        )

    elif (
        away_team_id
        is not None
    ):
        home_team_id = next(
            (
                team_id
                for team_id
                in team_ids
                if team_id
                != away_team_id
            ),
            None,
        )

    return (
        home_team_id,
        away_team_id,
    )


def add_target(df):
    df = df.copy()

    final_home_score = (
        df["scoreHome"]
        .iloc[-1]
    )

    final_away_score = (
        df["scoreAway"]
        .iloc[-1]
    )

    if (
        final_home_score
        == final_away_score
    ):
        raise ValueError(
            "Game ended tied; "
            "final score may be incomplete."
        )

    df["homeWin"] = int(
        final_home_score
        > final_away_score
    )

    return df


def _add_home_away_state(df):
    df = df.copy()

    (
        home_team_id,
        away_team_id,
    ) = get_team_ids(df)

    if (
        home_team_id
        is None
        or away_team_id
        is None
    ):
        raise IncompletePlayByPlayError(
            "Not enough play-by-play to determine "
            "home/away team IDs yet."
        )

    df[
        "homeTeamId"
    ] = int(
        home_team_id
    )

    df[
        "awayTeamId"
    ] = int(
        away_team_id
    )

    df[
        "homePossession"
    ] = (
        df[
            "possessionTeamId"
        ]
        .apply(
            lambda team_id:
                pd.NA
                if pd.isna(
                    team_id
                )
                else int(
                    int(team_id)
                    ==
                    int(
                        home_team_id
                    )
                )
        )
        .astype("Int64")
    )

    return df


def preprocess_live_game(df):
    """
    Process a partial or live game.

    Unlike preprocess_game(), this does
    not create homeWin because the final
    outcome may not yet be known.
    """

    df = df.copy()

    df = (
        add_elapsed_game_time(
            df
        )
    )

    df = (
        fill_scores(
            df
        )
    )

    df = (
        add_possession_state(
            df
        )
    )

    df = (
        _add_home_away_state(
            df
        )
    )

    df = (
        df
        .dropna(
            subset=[
                "homePossession"
            ]
        )
        .reset_index(
            drop=True
        )
    )

    if df.empty:
        raise IncompletePlayByPlayError(
            "Not enough play-by-play to build "
            "a usable possession state yet."
        )

    return df


def preprocess_game(df):
    df = (
        preprocess_live_game(
            df
        )
    )

    df = add_target(
        df
    )

    return df


if __name__ == "__main__":
    df = pd.read_csv(
        "data/raw/0022501188.csv"
    )

    df = preprocess_game(
        df
    )

    df.to_csv(
        "data/processed/"
        "0022501188.csv",
        index=False,
    )