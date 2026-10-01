import re

import pandas as pd

from nba_api.stats.static import (
    players as nba_players,
)

from replay_box_score import (
    build_player_aliases,
    get_full_player_name,
    normalize_player_alias,
    resolve_description_player,
)


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


def period_start_time(
    period,
):
    period = int(
        period
    )

    if period <= 4:
        return (
            720.0
            * (
                period - 1
            )
        )

    return (
        2880.0
        + 300.0
        * (
            period - 5
        )
    )


def period_end_time(
    period,
):
    period = int(
        period
    )

    if period <= 4:
        return (
            period
            * 720.0
        )

    return (
        2880.0
        + 300.0
        * (
            period - 4
        )
    )


_STATIC_NBA_PLAYERS = (
    nba_players.get_players()
)


_TEAM_ALIAS_OVERRIDES = {
    ("MIN", "miller"):
        1631159,

    ("SAS", "bryant"):
        1642868,

    ("CLE", "bryant"):
        1628418,

    ("DEN", "holmes ii"):
        1641747,

    ("MIL", "t antetokounmpo"):
        203648,

    ("MIL", "jackson jr"):
        1641748,
}


def resolve_static_player_alias(
    alias,
    team=None,
):
    """
    Resolve a player who has not yet appeared in the observed
    play-by-play prefix.

    Resolution rules:
      1. Unique exact full-name match.
      2. Unique active-player surname match.
      3. Otherwise remain unresolved.

    This uses static NBA metadata only and does not inspect
    future play-by-play rows.
    """

    normalized_alias = (
        normalize_player_alias(
            alias
        )
    )

    if not normalized_alias:
        return None

    normalized_team = (
        clean_text(
            team
        )
    )

    override = (
        _TEAM_ALIAS_OVERRIDES.get(
            (
                normalized_team,
                normalized_alias,
            )
        )
    )

    if override is not None:
        return override

    exact_matches = set()
    active_surname_matches = set()
    initial_surname_matches = set()

    alias_parts = (
        normalized_alias.split()
    )

    alias_initial = None
    alias_surname = None

    if (
        len(alias_parts) == 2
        and len(alias_parts[0]) == 1
    ):
        alias_initial = (
            alias_parts[0]
        )

        alias_surname = (
            alias_parts[1]
        )

    for player in _STATIC_NBA_PLAYERS:
        person_id = clean_person_id(
            player.get(
                "id"
            )
        )

        full_name = clean_text(
            player.get(
                "full_name",
                "",
            )
        )

        if (
            person_id is None
            or not full_name
        ):
            continue

        normalized_full = (
            normalize_player_alias(
                full_name
            )
        )

        if (
            normalized_alias
            == normalized_full
        ):
            exact_matches.add(
                person_id
            )

        parts = (
            normalized_full.split()
        )

        if not parts:
            continue

        surname = parts[-1]

        if (
            surname
            in {
                "jr",
                "sr",
                "ii",
                "iii",
                "iv",
            }
            and len(parts) >= 2
        ):
            surname = parts[-2]

        if (
            normalized_alias
            == surname
            and bool(
                player.get(
                    "is_active",
                    False,
                )
            )
        ):
            active_surname_matches.add(
                person_id
            )

        if (
            alias_initial is not None
            and alias_surname is not None
            and parts
            and parts[0]
            and parts[0][0]
            == alias_initial
            and surname
            == alias_surname
        ):
            initial_surname_matches.add(
                person_id
            )

    if len(exact_matches) == 1:
        return next(
            iter(
                exact_matches
            )
        )

    if (
        not exact_matches
        and len(
            initial_surname_matches
        ) == 1
    ):
        return next(
            iter(
                initial_surname_matches
            )
        )

    if (
        not exact_matches
        and not initial_surname_matches
        and len(
            active_surname_matches
        ) == 1
    ):
        return next(
            iter(
                active_surname_matches
            )
        )

    return None

def parse_substitution(
    row,
    alias_to_ids,
):
    description = clean_text(
        row.get(
            "description",
            "",
        )
    )

    match = re.match(
        r"^SUB:\s+(.+?)\s+FOR\s+(.+?)$",
        description,
        flags=re.IGNORECASE,
    )

    if match is None:
        return None

    incoming_alias = (
        match.group(1)
        .strip()
    )

    outgoing_alias = (
        match.group(2)
        .strip()
    )

    team = clean_text(
        row.get(
            "teamTricode",
            "",
        )
    )

    outgoing_id = (
        clean_person_id(
            row.get(
                "personId",
                None,
            )
        )
    )

    if outgoing_id is None:
        outgoing_id = (
            resolve_description_player(
                team,
                outgoing_alias,
                alias_to_ids,
            )
        )

    override_id = (
        _TEAM_ALIAS_OVERRIDES.get(
            (
                team,
                normalize_player_alias(
                    incoming_alias
                ),
            )
        )
    )

    if override_id is not None:
        incoming_id = (
            override_id
        )

    else:
        incoming_id = (
            resolve_description_player(
                team,
                incoming_alias,
                alias_to_ids,
            )
        )

    if incoming_id is None:
        incoming_id = (
            resolve_static_player_alias(
                incoming_alias,
                team=team,
            )
        )

    return {
        "team":
            team,

        "incoming_id":
            incoming_id,

        "incoming_alias":
            incoming_alias,

        "outgoing_id":
            outgoing_id,

        "outgoing_alias":
            outgoing_alias,
    }


def infer_period_starters(
    period_df,
    team,
    alias_to_ids,
    fallback_lineup=None,
):
    team_df = (
        period_df.loc[
            period_df[
                "teamTricode"
            ].astype(str)
            == team
        ]
        .copy()
        .reset_index(
            drop=True
        )
    )

    first_sub_role = {}
    observed_before_entry = set()
    already_entered = set()

    for _, row in (
        team_df.iterrows()
    ):
        action_type = clean_text(
            row.get(
                "actionType",
                "",
            )
        )

        person_id = clean_person_id(
            row.get(
                "personId",
                None,
            )
        )

        if action_type == "Substitution":
            substitution = (
                parse_substitution(
                    row,
                    alias_to_ids,
                )
            )

            if substitution is None:
                continue

            outgoing_id = (
                substitution[
                    "outgoing_id"
                ]
            )

            incoming_id = (
                substitution[
                    "incoming_id"
                ]
            )

            if outgoing_id is not None:
                first_sub_role.setdefault(
                    outgoing_id,
                    "OUT",
                )

            if incoming_id is not None:
                first_sub_role.setdefault(
                    incoming_id,
                    "IN",
                )

                already_entered.add(
                    incoming_id
                )

            continue

        if (
            person_id is not None
            and person_id
            not in already_entered
        ):
            observed_before_entry.add(
                person_id
            )

    starters = {
        person_id
        for (
            person_id,
            role,
        )
        in first_sub_role.items()
        if role == "OUT"
    }

    starters.update(
        observed_before_entry
    )

    period = int(
        period_df[
            "period"
        ].iloc[0]
    )

    if (
        period > 4
        and len(starters) == 4
        and fallback_lineup is not None
    ):
        fallback_candidates = (
            set(
                fallback_lineup
            )
            - starters
            - already_entered
        )

        if len(
            fallback_candidates
        ) == 1:
            starters.update(
                fallback_candidates
            )

    if len(starters) != 5:
        raise ValueError(
            f"Could not infer exactly five "
            f"{team} starters for period "
            f"{period}: "
            f"found {len(starters)}."
        )

    return starters


def infer_team_sides(
    df,
):
    home_team_id = None
    away_team_id = None

    if (
        "homeTeamId"
        in df.columns
        and df[
            "homeTeamId"
        ].notna().any()
    ):
        home_team_id = int(
            pd.to_numeric(
                df[
                    "homeTeamId"
                ],
                errors="coerce",
            )
            .dropna()
            .iloc[0]
        )

    if (
        "awayTeamId"
        in df.columns
        and df[
            "awayTeamId"
        ].notna().any()
    ):
        away_team_id = int(
            pd.to_numeric(
                df[
                    "awayTeamId"
                ],
                errors="coerce",
            )
            .dropna()
            .iloc[0]
        )

    team_id_to_tricode = {}

    for _, row in df.iterrows():
        team_id = clean_person_id(
            row.get(
                "teamId",
                None,
            )
        )

        tricode = clean_text(
            row.get(
                "teamTricode",
                "",
            )
        )

        if (
            team_id is not None
            and tricode
        ):
            team_id_to_tricode.setdefault(
                team_id,
                tricode,
            )

    if (
        home_team_id is not None
        and away_team_id is not None
    ):
        return (
            team_id_to_tricode[
                home_team_id
            ],
            team_id_to_tricode[
                away_team_id
            ],
        )

    previous_home = 0
    previous_away = 0

    home_team = None
    away_team = None

    for _, row in df.iterrows():
        home_score = int(
            row.get(
                "scoreHome",
                previous_home,
            )
        )

        away_score = int(
            row.get(
                "scoreAway",
                previous_away,
            )
        )

        team = clean_text(
            row.get(
                "teamTricode",
                "",
            )
        )

        if (
            team
            and home_score
            > previous_home
        ):
            home_team = team

        if (
            team
            and away_score
            > previous_away
        ):
            away_team = team

        previous_home = (
            home_score
        )

        previous_away = (
            away_score
        )

        if (
            home_team is not None
            and away_team is not None
        ):
            break

    if (
        home_team is None
        or away_team is None
    ):
        raise ValueError(
            "Could not resolve home and away teams."
        )

    return (
        home_team,
        away_team,
    )


def order_stint_events(
    period_df,
):
    """
    Adjust same-clock event ordering for stint plus/minus.

    NBA PBP can record substitutions between attempts of the
    same multi-free-throw sequence. Official plus/minus keeps
    the pre-substitution lineup through that free-throw sequence.

    Substitutions that occur before the first free throw remain
    in place, and substitutions outside multi-shot sequences are
    unchanged.
    """

    rows = []

    for _, clock_group in (
        period_df
        .groupby(
            "elapsedGameTime",
            sort=False,
        )
    ):
        pending_substitutions = []
        inside_multi_ft = False

        for _, row in (
            clock_group.iterrows()
        ):
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

            if (
                action_type
                == "Substitution"
                and inside_multi_ft
            ):
                pending_substitutions.append(
                    row
                )
                continue

            rows.append(
                row
            )

            if (
                action_type
                != "Free Throw"
            ):
                continue

            match = re.search(
                r"Free Throw(?: Flagrant)?\s+"
                r"(\d+)\s+of\s+(\d+)",
                description,
                flags=re.IGNORECASE,
            )

            if match is None:
                continue

            attempt = int(
                match.group(1)
            )

            total = int(
                match.group(2)
            )

            if (
                total > 1
                and attempt < total
            ):
                inside_multi_ft = True

            elif (
                inside_multi_ft
                and attempt == total
            ):
                inside_multi_ft = False

                rows.extend(
                    pending_substitutions
                )

                pending_substitutions = []

        rows.extend(
            pending_substitutions
        )

    if not rows:
        return (
            period_df
            .copy()
            .reset_index(
                drop=True
            )
        )

    return (
        pd.DataFrame(
            rows
        )
        .reset_index(
            drop=True
        )
    )


def build_live_stints(
    game_df,
):
    """
    Reconstruct player seconds and plus/minus using only
    play-by-play visible in game_df.

    Period lineups are inferred independently so lineup
    changes during quarter/halftime breaks do not require
    nonexistent substitution events.
    """

    if (
        game_df is None
        or game_df.empty
    ):
        raise ValueError(
            "Live stint tracking requires "
            "a non-empty game dataframe."
        )

    df = (
        game_df
        .copy()
        .reset_index(
            drop=True
        )
    )

    required = {
        "period",
        "elapsedGameTime",
        "teamTricode",
        "teamId",
        "personId",
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
            "Live stint tracking is missing "
            f"required fields: {sorted(missing)}"
        )

    df[
        "elapsedGameTime"
    ] = pd.to_numeric(
        df[
            "elapsedGameTime"
        ],
        errors="raise",
    )

    df[
        "period"
    ] = pd.to_numeric(
        df[
            "period"
        ],
        errors="raise",
    ).astype(int)

    df[
        "scoreHome"
    ] = pd.to_numeric(
        df[
            "scoreHome"
        ],
        errors="raise",
    ).astype(int)

    df[
        "scoreAway"
    ] = pd.to_numeric(
        df[
            "scoreAway"
        ],
        errors="raise",
    ).astype(int)

    df = (
        df
        .sort_values(
            [
                "elapsedGameTime",
                "actionId",
            ]
            if "actionId"
            in df.columns
            else [
                "elapsedGameTime",
            ],
            kind="mergesort",
        )
        .reset_index(
            drop=True
        )
    )

    original_home_diff = (
        df[
            "scoreHome"
        ]
        - df[
            "scoreAway"
        ]
    )

    df[
        "_homeDiffChange"
    ] = (
        original_home_diff
        .diff()
        .fillna(
            original_home_diff.iloc[0]
        )
        .astype(int)
    )

    (
        alias_to_ids,
        player_names,
    ) = build_player_aliases(
        df
    )

    (
        home_team,
        away_team,
    ) = infer_team_sides(
        df
    )

    teams = [
        home_team,
        away_team,
    ]

    player_seconds = {}
    player_plus_minus = {}
    player_team = {}
    player_display = {}

    lineup_snapshots = []
    substitutions = []

    cutoff = float(
        df[
            "elapsedGameTime"
        ].max()
    )

    observed_periods = sorted(
        df[
            "period"
        ].unique()
        .tolist()
    )

    previous_home_score = 0
    previous_away_score = 0

    def ensure_player(
        team,
        person_id,
        fallback="",
    ):
        if person_id is None:
            return

        key = (
            team,
            int(
                person_id
            ),
        )

        player_seconds.setdefault(
            key,
            0.0,
        )

        player_plus_minus.setdefault(
            key,
            0,
        )

        player_team[
            key
        ] = team

        player_display[
            key
        ] = (
            get_full_player_name(
                person_id
            )
            or player_names.get(
                key,
                fallback,
            )
            or fallback
            or str(
                person_id
            )
        )

    previous_period_lineups = None

    for period in observed_periods:
        start_time = (
            period_start_time(
                period
            )
        )

        if cutoff <= start_time:
            continue

        nominal_end = (
            period_end_time(
                period
            )
        )

        observed_end = min(
            cutoff,
            nominal_end,
        )

        if observed_end <= start_time:
            continue

        period_df = (
            df.loc[
                df[
                    "period"
                ]
                == period
            ]
            .copy()
            .reset_index(
                drop=True
            )
        )

        if period_df.empty:
            continue

        period_df = (
            order_stint_events(
                period_df
            )
        )

        lineups = {}

        for team in teams:
            starters = (
                infer_period_starters(
                    period_df,
                    team,
                    alias_to_ids,
                    fallback_lineup=(
                        previous_period_lineups.get(
                            team
                        )
                        if (
                            period > 4
                            and previous_period_lineups
                            is not None
                        )
                        else None
                    ),
                )
            )

            lineups[
                team
            ] = set(
                starters
            )

            for person_id in starters:
                ensure_player(
                    team,
                    person_id,
                )

        if (
            len(
                lineups[
                    home_team
                ]
            )
            != 5
            or len(
                lineups[
                    away_team
                ]
            )
            != 5
        ):
            raise RuntimeError(
                f"Invalid starting lineup "
                f"in period {period}."
            )

        current_time = (
            start_time
        )

        locked_plus_minus_lineups = None

        first_row = (
            period_df.iloc[0]
        )

        first_home_score = int(
            first_row[
                "scoreHome"
            ]
        )

        first_away_score = int(
            first_row[
                "scoreAway"
            ]
        )

        if period == observed_periods[0]:
            previous_home_score = (
                first_home_score
            )

            previous_away_score = (
                first_away_score
            )

        for _, row in (
            period_df.iterrows()
        ):
            event_time = float(
                row[
                    "elapsedGameTime"
                ]
            )

            if event_time > observed_end:
                break

            if event_time < current_time:
                raise RuntimeError(
                    "Play-by-play time moved backwards."
                )

            interval = (
                event_time
                - current_time
            )

            if interval > 0:
                for team in teams:
                    if len(
                        lineups[
                            team
                        ]
                    ) != 5:
                        raise RuntimeError(
                            f"{team} lineup does not "
                            f"contain five players at "
                            f"{current_time:.1f}."
                        )

                    for person_id in (
                        lineups[
                            team
                        ]
                    ):
                        key = (
                            team,
                            person_id,
                        )

                        player_seconds[
                            key
                        ] += interval

                current_time = (
                    event_time
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

            if action_type == "Foul":
                locked_plus_minus_lineups = {
                    team:
                        set(
                            lineups[
                                team
                            ]
                        )
                    for team
                    in teams
                }

            home_diff_change = int(
                row.get(
                    "_homeDiffChange",
                    0,
                )
            )

            plus_minus_lineups = (
                locked_plus_minus_lineups
                if (
                    clean_text(
                        row.get(
                            "actionType",
                            "",
                        )
                    )
                    == "Free Throw"
                    and locked_plus_minus_lineups
                    is not None
                )
                else lineups
            )

            if home_diff_change != 0:
                for person_id in (
                    plus_minus_lineups[
                        home_team
                    ]
                ):
                    player_plus_minus[
                        (
                            home_team,
                            person_id,
                        )
                    ] += (
                        home_diff_change
                    )

                for person_id in (
                    plus_minus_lineups[
                        away_team
                    ]
                ):
                    player_plus_minus[
                        (
                            away_team,
                            person_id,
                        )
                    ] -= (
                        home_diff_change
                    )

            if action_type == "Free Throw":
                match = re.search(
                    r"Free Throw(?: Flagrant)?\s+"
                    r"(\d+)\s+of\s+(\d+)",
                    description,
                    flags=re.IGNORECASE,
                )

                if match is not None:
                    attempt = int(
                        match.group(1)
                    )

                    total = int(
                        match.group(2)
                    )

                    if attempt == total:
                        locked_plus_minus_lineups = None

            elif (
                action_type
                not in {
                    "Foul",
                    "Substitution",
                    "Instant Replay",
                    "Rebound",
                    "Timeout",
                    "Violation",
                }
                and locked_plus_minus_lineups
                is not None
            ):
                locked_plus_minus_lineups = None

            if action_type != "Substitution":
                continue

            substitution = (
                parse_substitution(
                    row,
                    alias_to_ids,
                )
            )

            if substitution is None:
                continue

            team = (
                substitution[
                    "team"
                ]
            )

            outgoing_id = (
                substitution[
                    "outgoing_id"
                ]
            )

            incoming_id = (
                substitution[
                    "incoming_id"
                ]
            )

            if (
                outgoing_id is None
                or incoming_id is None
            ):
                raise ValueError(
                    "Could not resolve substitution: "
                    f"{row.get('description', '')}"
                )

            ensure_player(
                team,
                outgoing_id,
                substitution[
                    "outgoing_alias"
                ],
            )

            ensure_player(
                team,
                incoming_id,
                substitution[
                    "incoming_alias"
                ],
            )

            if outgoing_id not in (
                lineups[
                    team
                ]
            ):
                raise RuntimeError(
                    f"Outgoing player "
                    f"{outgoing_id} is not "
                    f"currently on court for "
                    f"{team}: "
                    f"{row.get('description', '')}"
                )

            if incoming_id in (
                lineups[
                    team
                ]
            ):
                raise RuntimeError(
                    f"Incoming player "
                    f"{incoming_id} is already "
                    f"on court for {team}: "
                    f"{row.get('description', '')}"
                )

            lineups[
                team
            ].remove(
                outgoing_id
            )

            lineups[
                team
            ].add(
                incoming_id
            )

            substitutions.append(
                {
                    "period":
                        int(
                            period
                        ),

                    "elapsedGameTime":
                        event_time,

                    "team":
                        team,

                    "outgoingPersonId":
                        outgoing_id,

                    "incomingPersonId":
                        incoming_id,

                    "description":
                        clean_text(
                            row.get(
                                "description",
                                "",
                            )
                        ),
                }
            )

            if len(
                lineups[
                    team
                ]
            ) != 5:
                raise RuntimeError(
                    f"{team} lineup has "
                    f"{len(lineups[team])} "
                    f"players after substitution."
                )

            lineup_snapshots.append(
                {
                    "period":
                        int(
                            period
                        ),

                    "elapsedGameTime":
                        event_time,

                    "team":
                        team,

                    "lineup":
                        tuple(
                            sorted(
                                lineups[
                                    team
                                ]
                            )
                        ),
                }
            )

        remaining = (
            observed_end
            - current_time
        )

        if remaining > 0:
            for team in teams:
                if len(
                    lineups[
                        team
                    ]
                ) != 5:
                    raise RuntimeError(
                        f"{team} lineup does not "
                        f"contain five players at "
                        f"end of period {period}."
                    )

                for person_id in (
                    lineups[
                        team
                    ]
                ):
                    player_seconds[
                        (
                            team,
                            person_id,
                        )
                    ] += (
                        remaining
                    )

        previous_period_lineups = {
            team:
                set(
                    lineups[
                        team
                    ]
                )

            for team
            in teams
        }

    rows = []

    for key in sorted(
        player_seconds
    ):
        team, person_id = key

        seconds = float(
            player_seconds[
                key
            ]
        )

        rows.append(
            {
                "Team":
                    team,

                "PersonId":
                    person_id,

                "Player":
                    player_display.get(
                        key,
                        str(
                            person_id
                        ),
                    ),

                "Seconds":
                    seconds,

                "Minutes":
                    (
                        seconds
                        / 60.0
                    ),

                "PlusMinus":
                    int(
                        player_plus_minus.get(
                            key,
                            0,
                        )
                    ),
            }
        )

    players = pd.DataFrame(
        rows
    )

    substitutions_df = pd.DataFrame(
        substitutions
    )

    snapshots_df = pd.DataFrame(
        lineup_snapshots
    )

    team_seconds = (
        players
        .groupby(
            "Team"
        )[
            "Seconds"
        ]
        .sum()
        .to_dict()
        if not players.empty
        else {}
    )

    expected_team_seconds = (
        5.0
        * sum(
            max(
                0.0,
                min(
                    cutoff,
                    period_end_time(
                        period
                    ),
                )
                - period_start_time(
                    period
                ),
            )
            for period
            in observed_periods
            if (
                cutoff
                > period_start_time(
                    period
                )
            )
        )
    )

    for team in teams:
        actual = float(
            team_seconds.get(
                team,
                0.0,
            )
        )

        if abs(
            actual
            - expected_team_seconds
        ) > 1e-6:
            raise RuntimeError(
                f"{team} player-seconds mismatch: "
                f"{actual:.3f} vs expected "
                f"{expected_team_seconds:.3f}."
            )

    return {
        "players":
            players,

        "substitutions":
            substitutions_df,

        "lineup_snapshots":
            snapshots_df,

        "home_team":
            home_team,

        "away_team":
            away_team,

        "cutoff_elapsed":
            cutoff,

        "expected_team_seconds":
            expected_team_seconds,

        "team_seconds":
            team_seconds,
    }
