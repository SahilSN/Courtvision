"""Replay-safe box-score reconstruction."""

import re
import unicodedata

import pandas as pd

from nba_api.stats.static import (
    players as nba_players,
)


_NBA_PLAYER_NAMES = {
    int(player["id"]):
        str(
            player.get(
                "full_name",
                "",
            )
        ).strip()

    for player
    in nba_players.get_players()
}


def get_full_player_name(
    person_id,
):
    try:
        person_id = int(
            person_id
        )
    except (
        TypeError,
        ValueError,
    ):
        return ""

    return (
        _NBA_PLAYER_NAMES.get(
            person_id,
            "",
        )
    )


def normalize_player_alias(
    value,
):
    if value is None:
        return ""

    try:
        if value != value:
            return ""
    except Exception:
        pass

    value = str(
        value
    ).strip()

    value = (
        unicodedata
        .normalize(
            "NFKD",
            value,
        )
        .encode(
            "ascii",
            "ignore",
        )
        .decode(
            "ascii"
        )
        .lower()
    )

    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def extract_description_player_alias(
    description,
):
    """
    Recover the player label NBA uses at the start of
    that player's own play-by-play description.

    Examples:
        Butler 1' Layup ...
            -> Butler

        Boston Jr. 29' 3PT ...
            -> Boston Jr.

        Jal. Williams 26' 3PT ...
            -> Jal. Williams

        Markkanen Free Throw ...
            -> Markkanen
    """
    if description is None:
        return ""

    try:
        if description != description:
            return ""
    except Exception:
        pass

    description = str(
        description
    ).strip()

    if not description:
        return ""

    patterns = [
        r"^(.+?)\s+\d+(?:\.\d+)?'",
        r"^(.+?)\s+Free Throw\b",
        r"^(.+?)\s+REBOUND\b",
        r"^(.+?)\s+.*Turnover\b",
        r"^(.+?)\s+STEAL\b",
        r"^(.+?)\s+BLOCK\b",
        r"^MISS\s+(.+?)\s+\d+(?:\.\d+)?'",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            description,
            flags=re.IGNORECASE,
        )

        if match is not None:
            return (
                match.group(1)
                .strip()
            )

    return ""


def build_player_aliases(
    df,
):
    alias_to_ids = {}
    player_names = {}

    def add_alias(
        team,
        person_id,
        alias,
    ):
        normalized = (
            normalize_player_alias(
                alias
            )
        )

        if not normalized:
            return

        alias_to_ids.setdefault(
            (
                team,
                normalized,
            ),
            set(),
        ).add(
            person_id
        )

    for _, row in df.iterrows():
        try:
            person_id = int(
                row.get(
                    "personId",
                    0,
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        if person_id <= 0:
            continue

        team = str(
            row.get(
                "teamTricode",
                "",
            )
        ).strip()

        if not team:
            continue

        player_name = str(
            row.get(
                "playerName",
                "",
            )
        ).strip()

        player_name_i = str(
            row.get(
                "playerNameI",
                "",
            )
        ).strip()

        description = str(
            row.get(
                "description",
                "",
            )
        ).strip()

        if (
            player_name
            and player_name.lower()
            != "nan"
        ):
            player_names.setdefault(
                (
                    team,
                    person_id,
                ),
                player_name,
            )

        add_alias(
            team,
            person_id,
            player_name,
        )

        add_alias(
            team,
            person_id,
            player_name_i,
        )

        # NBA descriptions sometimes use a different but
        # deterministic representation from playerName:
        #
        #   Butler III -> Butler
        #   Boston     -> Boston Jr.
        #   Williams   -> Jal. Williams / Jay. Williams
        #
        # Learn that representation only from rows where
        # personId is already known, so no identity guess
        # is required.
        description_alias = (
            extract_description_player_alias(
                description
            )
        )

        add_alias(
            team,
            person_id,
            description_alias,
        )

    return (
        alias_to_ids,
        player_names,
    )



def resolve_description_player(
    team,
    player_name,
    alias_to_ids,
):
    normalized = (
        normalize_player_alias(
            player_name
        )
    )

    if not normalized:
        return None

    exact = alias_to_ids.get(
        (
            team,
            normalized,
        ),
        set(),
    )

    if len(exact) == 1:
        return next(
            iter(
                exact
            )
        )

    # Description credits sometimes use:
    #
    #   G. Antetokounmpo
    #
    # while playerName is:
    #
    #   Antetokounmpo
    #
    tokens = (
        normalized.split()
    )

    if (
        len(tokens) >= 2
        and len(
            tokens[0]
        ) == 1
    ):
        surname_alias = " ".join(
            tokens[
                1:
            ]
        )

        surname_match = (
            alias_to_ids.get(
                (
                    team,
                    surname_alias,
                ),
                set(),
            )
        )

        if len(
            surname_match
        ) == 1:
            return next(
                iter(
                    surname_match
                )
            )

    return None


def build_replay_box_score(
    game_df,
):
    """
    Reconstruct traditional player statistics using only
    play-by-play rows visible through the current replay state.

    Player identity is based primarily on NBA personId.
    """

    df = (
        game_df
        .copy()
        .reset_index(
            drop=True
        )
    )

    required = {
        "teamTricode",
        "playerName",
        "actionType",
        "description",
        "scoreHome",
        "scoreAway",
    }

    missing = (
        required
        - set(
            df.columns
        )
    )

    if missing:
        raise ValueError(
            "Replay box score is missing required fields: "
            f"{sorted(missing)}"
        )

    (
        alias_to_ids,
        player_names,
    ) = build_player_aliases(
        df
    )

    players = {}


    def clean_text(
        value,
    ):
        if value is None:
            return ""

        try:
            if value != value:
                return ""
        except Exception:
            pass

        return str(
            value
        ).strip()


    def clean_person_id(
        value,
    ):
        try:
            value = int(
                value
            )

            if value > 0:
                return value

        except (
            TypeError,
            ValueError,
        ):
            pass

        return None


    def ensure_player(
        team,
        player,
        person_id=None,
    ):
        team = clean_text(
            team
        )

        player = clean_text(
            player
        )

        person_id = clean_person_id(
            person_id
        )

        if not team:
            return None

        if person_id is None:
            person_id = (
                resolve_description_player(
                    team,
                    player,
                    alias_to_ids,
                )
            )

        if person_id is not None:
            key = (
                team,
                person_id,
            )

            display_name = (
                get_full_player_name(
                    person_id
                )
                or player_names.get(
                    key,
                    player,
                )
            )

        else:
            normalized = (
                normalize_player_alias(
                    player
                )
            )

            if not normalized:
                return None

            key = (
                team,
                f"name:{normalized}",
            )

            display_name = player

        if key not in players:
            players[
                key
            ] = {
                "Team":
                    team,

                "PersonId":
                    person_id,

                "Player":
                    display_name,

                "PTS":
                    0,

                "REB":
                    0,

                "AST":
                    0,

                "STL":
                    0,

                "BLK":
                    0,

                "TO":
                    0,

                "FGM":
                    0,

                "FGA":
                    0,

                "3PM":
                    0,

                "3PA":
                    0,

                "FTM":
                    0,

                "FTA":
                    0,
            }

        return players[
            key
        ]


    def extract_assister(
        description,
    ):
        matches = re.findall(
            r"\(([^()]+?)\s+\d+\s+AST\)",
            clean_text(
                description
            ),
        )

        if not matches:
            return None

        return (
            matches[-1]
            .strip()
        )


    previous_home_score = 0
    previous_away_score = 0

    for _, row in (
        df.iterrows()
    ):
        team = clean_text(
            row.get(
                "teamTricode",
                "",
            )
        )

        player = clean_text(
            row.get(
                "playerName",
                "",
            )
        )

        person_id = clean_person_id(
            row.get(
                "personId",
                None,
            )
        )

        action_type = clean_text(
            row.get(
                "actionType",
                "",
            )
        )

        description = clean_text(
            row.get(
                "description",
                "",
            )
        )

        current_home_score = int(
            float(
                row.get(
                    "scoreHome",
                    previous_home_score,
                )
            )
        )

        current_away_score = int(
            float(
                row.get(
                    "scoreAway",
                    previous_away_score,
                )
            )
        )

        home_delta = max(
            0,
            current_home_score
            - previous_home_score,
        )

        away_delta = max(
            0,
            current_away_score
            - previous_away_score,
        )

        points_added = (
            home_delta
            + away_delta
        )

        stats = ensure_player(
            team,
            player,
            person_id,
        )

        if action_type in {
            "Made Shot",
            "Missed Shot",
        }:
            if stats is not None:
                stats[
                    "FGA"
                ] += 1

                is_three = (
                    "3PT"
                    in description.upper()
                )

                if is_three:
                    stats[
                        "3PA"
                    ] += 1

                if (
                    action_type
                    == "Made Shot"
                ):
                    stats[
                        "FGM"
                    ] += 1

                    if is_three:
                        stats[
                            "3PM"
                        ] += 1

                    stats[
                        "PTS"
                    ] += points_added

                    assister = (
                        extract_assister(
                            description
                        )
                    )

                    if assister:
                        assist_stats = (
                            ensure_player(
                                team,
                                assister,
                            )
                        )

                        if (
                            assist_stats
                            is not None
                        ):
                            assist_stats[
                                "AST"
                            ] += 1

        elif action_type == "Free Throw":
            if stats is not None:
                stats[
                    "FTA"
                ] += 1

                # NBA PBP V3 frequently leaves shotResult
                # blank for free throws, and technical FT
                # scoreboard updates can be offset from the
                # event row. The description reliably marks
                # misses with a leading "MISS".
                made = not (
                    description
                    .upper()
                    .startswith(
                        "MISS "
                    )
                )

                if made:
                    stats[
                        "FTM"
                    ] += 1

                    stats[
                        "PTS"
                    ] += 1

        elif action_type == "Rebound":
            if stats is not None:
                stats[
                    "REB"
                ] += 1

        elif action_type == "Turnover":
            if stats is not None:
                stats[
                    "TO"
                ] += 1

        upper_description = (
            description.upper()
        )

        if (
            stats is not None
            and " STEAL "
            in (
                f" {upper_description} "
            )
        ):
            stats[
                "STL"
            ] += 1

        if (
            stats is not None
            and " BLOCK "
            in (
                f" {upper_description} "
            )
        ):
            stats[
                "BLK"
            ] += 1

        previous_home_score = (
            current_home_score
        )

        previous_away_score = (
            current_away_score
        )


    rows = []

    for stats in (
        players.values()
    ):
        visible_total = sum(
            stats[
                column
            ]
            for column in [
                "PTS",
                "REB",
                "AST",
                "STL",
                "BLK",
                "TO",
                "FGA",
                "FTA",
            ]
        )

        if visible_total == 0:
            continue

        rows.append(
            {
                "Team":
                    stats[
                        "Team"
                    ],

                "PersonId":
                    stats[
                        "PersonId"
                    ],

                "Player":
                    stats[
                        "Player"
                    ],

                "PTS":
                    stats[
                        "PTS"
                    ],

                "REB":
                    stats[
                        "REB"
                    ],

                "AST":
                    stats[
                        "AST"
                    ],

                "STL":
                    stats[
                        "STL"
                    ],

                "BLK":
                    stats[
                        "BLK"
                    ],

                "TO":
                    stats[
                        "TO"
                    ],

                "FG":
                    (
                        f"{stats['FGM']}"
                        f"-{stats['FGA']}"
                    ),

                "3PT":
                    (
                        f"{stats['3PM']}"
                        f"-{stats['3PA']}"
                    ),

                "FT":
                    (
                        f"{stats['FTM']}"
                        f"-{stats['FTA']}"
                    ),
            }
        )

    columns = [
        "Team",
        "PersonId",
        "Player",
        "PTS",
        "REB",
        "AST",
        "STL",
        "BLK",
        "TO",
        "FG",
        "3PT",
        "FT",
    ]

    if not rows:
        return pd.DataFrame(
            columns=columns
        )

    box_df = pd.DataFrame(
        rows
    )

    return (
        box_df
        .sort_values(
            [
                "Team",
                "PTS",
                "REB",
                "AST",
                "Player",
            ],
            ascending=[
                True,
                False,
                False,
                False,
                True,
            ],
            kind="mergesort",
        )
        .reset_index(
            drop=True
        )
    )
