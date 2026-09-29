import re
import unicodedata

import numpy as np
import pandas as pd


# ============================================================
# Shared-credit policy
# ============================================================

ASSIST_SHARE = 0.25
STEAL_SHARE = 0.50
BLOCK_SHARE = 0.50


# ============================================================
# Text / player helpers
# ============================================================

def clean_text(
    value,
):
    if pd.isna(value):
        return ""

    return str(
        value
    ).strip()


def normalize_name(
    value,
):
    text = clean_text(
        value
    )

    text = unicodedata.normalize(
        "NFKD",
        text,
    )

    text = "".join(
        character
        for character in text
        if not unicodedata.combining(
            character
        )
    )

    text = text.casefold()

    text = re.sub(
        r"[^a-z0-9]+",
        "",
        text,
    )

    return text


def normalize_person_id(
    value,
):
    try:
        if pd.isna(value):
            return np.nan

        return int(
            float(value)
        )

    except (
        TypeError,
        ValueError,
    ):
        return np.nan


# ============================================================
# Parse secondary contributors from NBA descriptions
# ============================================================

def parse_stat_credit(
    description,
    stat,
):
    """
    Examples commonly seen in NBA PBP:

        (Edwards 8 AST)
        (Harden 2 STL)
        (Gobert 3 BLK)
    """

    description = clean_text(
        description
    )

    pattern = (
        rf"\(([^()]*)\s+"
        rf"\d+\s+{stat}\)"
    )

    matches = re.findall(
        pattern,
        description,
        flags=re.IGNORECASE,
    )

    if not matches:
        return None

    return clean_text(
        matches[-1]
    )


def parse_assister(
    description,
):
    return parse_stat_credit(
        description,
        "AST",
    )


def parse_stealer(
    description,
):
    return parse_stat_credit(
        description,
        "STL",
    )


def parse_blocker(
    description,
):
    blocker = parse_stat_credit(
        description,
        "BLK",
    )

    if blocker:
        return blocker

    description = clean_text(
        description
    )

    # Support descriptions that use
    # "(Player BLOCK)" without a count.
    matches = re.findall(
        r"\(([^()]*)\s+BLOCK\)",
        description,
        flags=re.IGNORECASE,
    )

    if not matches:
        return None

    return clean_text(
        matches[-1]
    )


# ============================================================
# Player lookup
# ============================================================

def build_player_lookup(
    game_df,
):
    columns = [
        column
        for column in [
            "personId",
            "playerName",
            "teamTricode",
        ]
        if column
        in game_df.columns
    ]

    if len(columns) < 3:
        return []

    players = (
        game_df[
            columns
        ]
        .dropna(
            subset=[
                "personId",
                "playerName",
                "teamTricode",
            ]
        )
        .drop_duplicates()
        .copy()
    )

    lookup = []

    for _, row in (
        players.iterrows()
    ):
        player_name = clean_text(
            row[
                "playerName"
            ]
        )

        team = clean_text(
            row[
                "teamTricode"
            ]
        )

        lookup.append(
            {
                "personId":
                    normalize_person_id(
                        row[
                            "personId"
                        ]
                    ),

                "playerName":
                    player_name,

                "teamTricode":
                    team,

                "normalizedName":
                    normalize_name(
                        player_name
                    ),
            }
        )

    return lookup


def resolve_player(
    name,
    lookup,
    expected_team=None,
):
    if not name:
        return None

    normalized = (
        normalize_name(
            name
        )
    )

    if not normalized:
        return None

    candidates = (
        lookup
    )

    if expected_team:
        candidates = [
            player
            for player in candidates
            if player[
                "teamTricode"
            ]
            == expected_team
        ]

    # Exact normalized match.
    exact = [
        player
        for player in candidates
        if player[
            "normalizedName"
        ]
        == normalized
    ]

    if len(exact) == 1:
        return exact[0]

    # Allow one normalized name to be a
    # suffix of the other. This helps when
    # the description and playerName fields
    # differ slightly in formatting.
    partial = [
        player
        for player in candidates
        if (
            player[
                "normalizedName"
            ].endswith(
                normalized
            )
            or normalized.endswith(
                player[
                    "normalizedName"
                ]
            )
        )
    ]

    unique = {}

    for player in partial:
        unique[
            (
                player[
                    "personId"
                ],
                player[
                    "teamTricode"
                ],
            )
        ] = player

    partial = list(
        unique.values()
    )

    if len(partial) == 1:
        return partial[0]

    return None


# ============================================================
# Team helpers
# ============================================================

def opposite_team(
    team,
    home_team,
    away_team,
):
    if team == home_team:
        return away_team

    if team == away_team:
        return home_team

    return None


# ============================================================
# Same-clock sequence lookup
# ============================================================

def add_sequence_ids(
    game_df,
):
    df = (
        game_df.copy()
        .reset_index(
            drop=True
        )
    )

    new_sequence = (
        (
            df[
                "period"
            ]
            != df[
                "period"
            ].shift(1)
        )
        | (
            df[
                "clock"
            ]
            != df[
                "clock"
            ].shift(1)
        )
    )

    df[
        "sequenceId"
    ] = (
        new_sequence
        .cumsum()
        .astype(int)
    )

    return df


def find_sequence_secondary_player(
    sequence,
    expected_team,
    keywords,
    lookup,
):
    """
    Fallback for blocks / steals that appear
    on their own PBP row rather than inside
    the primary event description.
    """

    for _, row in (
        sequence.iterrows()
    ):
        if (
            clean_text(
                row.get(
                    "teamTricode",
                    "",
                )
            )
            != expected_team
        ):
            continue

        combined = (
            clean_text(
                row.get(
                    "actionType",
                    "",
                )
            )
            + " "
            + clean_text(
                row.get(
                    "description",
                    "",
                )
            )
        ).upper()

        if not any(
            keyword
            in combined
            for keyword
            in keywords
        ):
            continue

        player = resolve_player(
            row.get(
                "playerName"
            ),
            lookup,
            expected_team=(
                expected_team
            ),
        )

        if player:
            return player

    return None


# ============================================================
# Attribution-row constructors
# ============================================================

def make_credit_row(
    source_row,
    player,
    player_wpa,
    credit_share,
    credit_role,
    shared,
):
    row = (
        source_row.copy()
    )

    original_wpa = float(
        source_row[
            "playerWPA"
        ]
    )

    row[
        "sourcePlayerWPA"
    ] = original_wpa

    row[
        "sourcePlayerWPAPoints"
    ] = (
        original_wpa
        * 100.0
    )

    row[
        "personId"
    ] = (
        player[
            "personId"
        ]
    )

    row[
        "playerName"
    ] = (
        player[
            "playerName"
        ]
    )

    row[
        "teamTricode"
    ] = (
        player[
            "teamTricode"
        ]
    )

    row[
        "playerWPA"
    ] = float(
        player_wpa
    )

    row[
        "playerWPAPoints"
    ] = (
        float(
            player_wpa
        )
        * 100.0
    )

    row[
        "creditShare"
    ] = float(
        credit_share
    )

    row[
        "creditRole"
    ] = (
        credit_role
    )

    row[
        "sharedCreditApplied"
    ] = bool(
        shared
    )

    return row


def primary_player_from_row(
    row,
):
    return {
        "personId":
            normalize_person_id(
                row.get(
                    "personId"
                )
            ),

        "playerName":
            clean_text(
                row.get(
                    "playerName",
                    "",
                )
            ),

        "teamTricode":
            clean_text(
                row.get(
                    "teamTricode",
                    "",
                )
            ),
    }


# ============================================================
# Scoring + assist attribution
# ============================================================

def split_scoring_credit(
    row,
    lookup,
):
    primary = (
        primary_player_from_row(
            row
        )
    )

    original_wpa = float(
        row[
            "playerWPA"
        ]
    )

    assister_name = (
        parse_assister(
            row.get(
                "description",
                "",
            )
        )
    )

    if not assister_name:
        return [
            make_credit_row(
                row,
                primary,
                original_wpa,
                1.0,
                "scorer",
                False,
            )
        ]

    assister = (
        resolve_player(
            assister_name,
            lookup,
            expected_team=(
                primary[
                    "teamTricode"
                ]
            ),
        )
    )

    if (
        assister is None
        or (
            not pd.isna(
                primary[
                    "personId"
                ]
            )
            and (
                assister[
                    "personId"
                ]
                == primary[
                    "personId"
                ]
            )
        )
    ):
        return [
            make_credit_row(
                row,
                primary,
                original_wpa,
                1.0,
                "scorer",
                False,
            )
        ]

    scorer_share = (
        1.0
        - ASSIST_SHARE
    )

    return [
        make_credit_row(
            row,
            primary,
            (
                original_wpa
                * scorer_share
            ),
            scorer_share,
            "scorer",
            True,
        ),

        make_credit_row(
            row,
            assister,
            (
                original_wpa
                * ASSIST_SHARE
            ),
            ASSIST_SHARE,
            "assister",
            True,
        ),
    ]


# ============================================================
# Turnover + steal attribution
# ============================================================

def split_turnover_credit(
    row,
    sequence,
    lookup,
    home_team,
    away_team,
):
    primary = (
        primary_player_from_row(
            row
        )
    )

    original_wpa = float(
        row[
            "playerWPA"
        ]
    )

    defensive_team = (
        opposite_team(
            primary[
                "teamTricode"
            ],
            home_team,
            away_team,
        )
    )

    stealer_name = (
        parse_stealer(
            row.get(
                "description",
                "",
            )
        )
    )

    stealer = None

    if stealer_name:
        stealer = (
            resolve_player(
                stealer_name,
                lookup,
                expected_team=(
                    defensive_team
                ),
            )
        )

    if (
        stealer is None
        and defensive_team
    ):
        stealer = (
            find_sequence_secondary_player(
                sequence,
                defensive_team,
                [
                    "STEAL",
                    "STL",
                ],
                lookup,
            )
        )

    if stealer is None:
        return [
            make_credit_row(
                row,
                primary,
                original_wpa,
                1.0,
                "turnover",
                False,
            )
        ]

    turnover_share = (
        1.0
        - STEAL_SHARE
    )

    # The stealer is on the opposite team,
    # so the same event has opposite sign
    # from their perspective.
    stealer_wpa = (
        -original_wpa
        * STEAL_SHARE
    )

    return [
        make_credit_row(
            row,
            primary,
            (
                original_wpa
                * turnover_share
            ),
            turnover_share,
            "turnover",
            True,
        ),

        make_credit_row(
            row,
            stealer,
            stealer_wpa,
            STEAL_SHARE,
            "stealer",
            True,
        ),
    ]


# ============================================================
# Miss + block attribution
# ============================================================

def split_block_credit(
    row,
    sequence,
    lookup,
    home_team,
    away_team,
):
    primary = (
        primary_player_from_row(
            row
        )
    )

    original_wpa = float(
        row[
            "playerWPA"
        ]
    )

    defensive_team = (
        opposite_team(
            primary[
                "teamTricode"
            ],
            home_team,
            away_team,
        )
    )

    blocker_name = (
        parse_blocker(
            row.get(
                "description",
                "",
            )
        )
    )

    blocker = None

    if blocker_name:
        blocker = (
            resolve_player(
                blocker_name,
                lookup,
                expected_team=(
                    defensive_team
                ),
            )
        )

    if (
        blocker is None
        and defensive_team
    ):
        blocker = (
            find_sequence_secondary_player(
                sequence,
                defensive_team,
                [
                    "BLOCK",
                    "BLK",
                ],
                lookup,
            )
        )

    if blocker is None:
        return [
            make_credit_row(
                row,
                primary,
                original_wpa,
                1.0,
                "shooter",
                False,
            )
        ]

    shooter_share = (
        1.0
        - BLOCK_SHARE
    )

    blocker_wpa = (
        -original_wpa
        * BLOCK_SHARE
    )

    return [
        make_credit_row(
            row,
            primary,
            (
                original_wpa
                * shooter_share
            ),
            shooter_share,
            "shooter",
            True,
        ),

        make_credit_row(
            row,
            blocker,
            blocker_wpa,
            BLOCK_SHARE,
            "blocker",
            True,
        ),
    ]


# ============================================================
# Other attribution
# ============================================================

def keep_primary_credit(
    row,
):
    primary = (
        primary_player_from_row(
            row
        )
    )

    role = clean_text(
        row.get(
            "attributionType",
            "primary",
        )
    ).casefold()

    if role == "rebound":
        role = "rebounder"

    return [
        make_credit_row(
            row,
            primary,
            float(
                row[
                    "playerWPA"
                ]
            ),
            1.0,
            role,
            False,
        )
    ]


# ============================================================
# Public API
# ============================================================

def apply_shared_credit(
    events,
    game_df,
    home_team,
    away_team,
):
    """
    Apply assist / steal / block shared-credit
    attribution without changing the frozen
    WPA v3 counterfactual event values.

    Important:
      - assisted scoring divides the same
        team-relative event credit between
        scorer and assister.
      - steals / blocks divide the event's
        absolute attribution budget between
        opposing players, with each player's
        value expressed from their own team's
        perspective.
    """

    if events.empty:
        return events.copy()

    lookup = (
        build_player_lookup(
            game_df
        )
    )

    sequence_df = (
        add_sequence_ids(
            game_df
        )
    )

    sequence_lookup = {
        sequence_id:
            sequence.copy()

        for (
            sequence_id,
            sequence,
        )
        in sequence_df.groupby(
            "sequenceId",
            sort=False,
        )
    }

    output_rows = []

    # Each row entering this layer represents one
    # original WPA v3 player attribution. Preserve
    # a stable identifier so scorer/assister,
    # turnover/stealer, and shooter/blocker splits
    # can later be recombined exactly.
    events = (
        events.copy()
        .reset_index(
            drop=True
        )
    )

    events[
        "sourceAttributionId"
    ] = range(
        len(events)
    )

    for _, row in (
        events.iterrows()
    ):
        attribution_type = (
            clean_text(
                row.get(
                    "attributionType",
                    "",
                )
            )
        )

        sequence_id = int(
            row[
                "sequenceId"
            ]
        )

        sequence = (
            sequence_lookup.get(
                sequence_id,
                sequence_df.iloc[
                    0:0
                ].copy(),
            )
        )

        if (
            attribution_type
            == "Scoring"
        ):
            allocations = (
                split_scoring_credit(
                    row,
                    lookup,
                )
            )

        elif (
            attribution_type
            == "Turnover"
        ):
            allocations = (
                split_turnover_credit(
                    row,
                    sequence,
                    lookup,
                    home_team,
                    away_team,
                )
            )

        elif (
            attribution_type
            == "Missed Shot"
        ):
            allocations = (
                split_block_credit(
                    row,
                    sequence,
                    lookup,
                    home_team,
                    away_team,
                )
            )

        else:
            allocations = (
                keep_primary_credit(
                    row
                )
            )

        output_rows.extend(
            allocations
        )

    result = pd.DataFrame(
        output_rows
    )

    if not result.empty:
        result = (
            result
            .sort_values(
                [
                    "sequenceId",
                    "creditRole",
                ],
                kind="mergesort",
            )
            .reset_index(
                drop=True
            )
        )

    return result
