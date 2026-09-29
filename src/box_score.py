from __future__ import annotations

import re

import pandas as pd

from nba_api.stats.endpoints import (
    boxscoreadvancedv3,
    boxscoretraditionalv3,
)


# ============================================================
# Helpers
# ============================================================

def normalize_game_id(
    game_id,
):
    return str(
        game_id
    ).zfill(10)


def clean_text(
    value,
):
    if pd.isna(
        value
    ):
        return ""

    return str(
        value
    ).strip()


def format_minutes(
    value,
):
    """
    Normalize NBA box-score minute strings.

    Handles common values such as:
        "37:42"
        "PT37M42.00S"
        ""
    """

    text = clean_text(
        value
    )

    if not text:
        return ""

    if text.startswith(
        "PT"
    ):
        match = re.fullmatch(
            r"PT(?:(\d+)M)?"
            r"(\d+(?:\.\d+)?)S",
            text,
        )

        if match is None:
            return text

        minutes = int(
            match.group(1)
            or 0
        )

        seconds = int(
            float(
                match.group(2)
            )
        )

        return (
            f"{minutes}:"
            f"{seconds:02d}"
        )

    return text


def make_full_name(
    row,
):
    first_name = clean_text(
        row.get(
            "firstName",
            "",
        )
    )

    family_name = clean_text(
        row.get(
            "familyName",
            "",
        )
    )

    full_name = (
        f"{first_name} "
        f"{family_name}"
    ).strip()

    if full_name:
        return full_name

    return clean_text(
        row.get(
            "nameI",
            "",
        )
    )


def safe_numeric(
    series,
):
    return pd.to_numeric(
        series,
        errors="coerce",
    )


# ============================================================
# Traditional box score
# ============================================================

def fetch_traditional_box_score(
    game_id,
    timeout=60,
):
    game_id = normalize_game_id(
        game_id
    )

    endpoint = (
        boxscoretraditionalv3
        .BoxScoreTraditionalV3(
            game_id=game_id,
            timeout=timeout,
        )
    )

    players = (
        endpoint
        .player_stats
        .get_data_frame()
        .copy()
    )

    teams = (
        endpoint
        .team_stats
        .get_data_frame()
        .copy()
    )

    return (
        players,
        teams,
    )


# ============================================================
# Advanced box score
# ============================================================

def fetch_advanced_box_score(
    game_id,
    timeout=60,
):
    game_id = normalize_game_id(
        game_id
    )

    endpoint = (
        boxscoreadvancedv3
        .BoxScoreAdvancedV3(
            game_id=game_id,
            timeout=timeout,
        )
    )

    players = (
        endpoint
        .player_stats
        .get_data_frame()
        .copy()
    )

    teams = (
        endpoint
        .team_stats
        .get_data_frame()
        .copy()
    )

    return (
        players,
        teams,
    )


# ============================================================
# Clean player data
# ============================================================

def prepare_traditional_players(
    df,
):
    df = df.copy()

    if df.empty:
        return df

    df[
        "fullName"
    ] = df.apply(
        make_full_name,
        axis=1,
    )

    df[
        "minutesDisplay"
    ] = df[
        "minutes"
    ].apply(
        format_minutes
    )

    numeric_columns = [
        "fieldGoalsMade",
        "fieldGoalsAttempted",
        "fieldGoalsPercentage",
        "threePointersMade",
        "threePointersAttempted",
        "threePointersPercentage",
        "freeThrowsMade",
        "freeThrowsAttempted",
        "freeThrowsPercentage",
        "reboundsOffensive",
        "reboundsDefensive",
        "reboundsTotal",
        "assists",
        "steals",
        "blocks",
        "turnovers",
        "foulsPersonal",
        "points",
        "plusMinusPoints",
    ]

    for column in (
        numeric_columns
    ):
        if column in df.columns:
            df[
                column
            ] = safe_numeric(
                df[
                    column
                ]
            )

    # V3 typically stores a position for
    # starters and an empty string for bench
    # players.
    df[
        "starter"
    ] = (
        df[
            "position"
        ]
        .fillna("")
        .astype(str)
        .str.strip()
        .ne("")
    )

    return df


def prepare_advanced_players(
    df,
):
    df = df.copy()

    if df.empty:
        return df

    numeric_columns = [
        "offensiveRating",
        "defensiveRating",
        "netRating",
        "assistPercentage",
        "assistToTurnover",
        "assistRatio",
        "offensiveReboundPercentage",
        "defensiveReboundPercentage",
        "reboundPercentage",
        "turnoverRatio",
        "effectiveFieldGoalPercentage",
        "trueShootingPercentage",
        "usagePercentage",
        "pace",
        "possessions",
        "PIE",
    ]

    for column in (
        numeric_columns
    ):
        if column in df.columns:
            df[
                column
            ] = safe_numeric(
                df[
                    column
                ]
            )

    return df


# ============================================================
# Merge traditional + advanced
# ============================================================

def merge_player_stats(
    traditional,
    advanced,
):
    traditional = (
        prepare_traditional_players(
            traditional
        )
    )

    if (
        advanced is None
        or advanced.empty
    ):
        return traditional

    advanced = (
        prepare_advanced_players(
            advanced
        )
    )

    merge_keys = [
        "gameId",
        "teamId",
        "personId",
    ]

    advanced_columns = [
        column
        for column in [
            "gameId",
            "teamId",
            "personId",
            "offensiveRating",
            "defensiveRating",
            "netRating",
            "assistPercentage",
            "assistToTurnover",
            "assistRatio",
            "offensiveReboundPercentage",
            "defensiveReboundPercentage",
            "reboundPercentage",
            "turnoverRatio",
            "effectiveFieldGoalPercentage",
            "trueShootingPercentage",
            "usagePercentage",
            "pace",
            "possessions",
            "PIE",
        ]
        if column
        in advanced.columns
    ]

    merged = traditional.merge(
        advanced[
            advanced_columns
        ],
        on=merge_keys,
        how="left",
        validate="one_to_one",
    )

    return merged


# ============================================================
# Public API
# ============================================================

def fetch_box_score(
    game_id,
    timeout=60,
):
    """
    Fetch Courtvision's box-score representation.

    Traditional statistics are required.
    Advanced statistics are optional: if the
    advanced endpoint fails, the traditional
    box score still renders normally.
    """

    game_id = normalize_game_id(
        game_id
    )

    (
        traditional_players,
        traditional_teams,
    ) = fetch_traditional_box_score(
        game_id,
        timeout=timeout,
    )

    advanced_players = None
    advanced_teams = None
    advanced_error = None

    try:
        (
            advanced_players,
            advanced_teams,
        ) = fetch_advanced_box_score(
            game_id,
            timeout=timeout,
        )

    except Exception as error:
        # Do not make the normal box score
        # unavailable just because advanced
        # statistics fail.
        advanced_error = str(
            error
        )

    players = merge_player_stats(
        traditional_players,
        advanced_players,
    )

    return {
        "game_id":
            game_id,

        "players":
            players,

        "traditional_teams":
            traditional_teams,

        "advanced_teams":
            advanced_teams,

        "advanced_available":
            (
                advanced_players
                is not None
                and not advanced_players.empty
            ),

        "advanced_error":
            advanced_error,
    }


def get_team_players(
    box_score,
    team_tricode,
):
    players = (
        box_score[
            "players"
        ]
    )

    return (
        players[
            players[
                "teamTricode"
            ]
            == team_tricode
        ]
        .copy()
        .reset_index(
            drop=True
        )
    )


if __name__ == "__main__":
    import argparse

    parser = (
        argparse.ArgumentParser()
    )

    parser.add_argument(
        "game_id",
    )

    args = (
        parser.parse_args()
    )

    result = fetch_box_score(
        args.game_id
    )

    print(
        result[
            "players"
        ].to_string(
            index=False
        )
    )

    print(
        "\nAdvanced available:",
        result[
            "advanced_available"
        ],
    )
