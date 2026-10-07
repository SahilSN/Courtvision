import re
import unicodedata
from functools import lru_cache

import pandas as pd
import requests

from nba_api.stats.endpoints import commonteamroster
from nba_api.stats.static import players as nba_players
from nba_api.stats.static import teams as nba_teams

from game_catalog import (
    fetch_games_for_date_from_scoreboard,
)


ESPN_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/"
    "sports/basketball/nba/scoreboard"
)

ESPN_SUMMARY_URL = (
    "https://site.api.espn.com/apis/site/v2/"
    "sports/basketball/nba/summary"
)


class ESPNLiveFeedError(RuntimeError):
    """ESPN live data could not be resolved or normalized."""


def normalize_name(
    value,
):
    value = unicodedata.normalize(
        "NFKD",
        str(
            value
            or ""
        ),
    )

    value = "".join(
        character
        for character in value
        if not unicodedata.combining(
            character
        )
    )

    value = value.lower()

    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    return " ".join(
        value.split()
    )


_NBA_TEAMS_BY_ID = {
    int(
        team["id"]
    ):
        team
    for team in nba_teams.get_teams()
}


@lru_cache(maxsize=1)
def static_player_name_map():
    lookup = {}

    for player in (
        nba_players.get_players()
    ):
        name = normalize_name(
            player.get(
                "full_name",
                "",
            )
        )

        if not name:
            continue

        lookup.setdefault(
            name,
            [],
        ).append(
            {
                "id":
                    int(
                        player["id"]
                    ),

                "name":
                    player.get(
                        "full_name",
                        "",
                    ),
            }
        )

    return lookup


@lru_cache(maxsize=64)
def current_roster_name_map(
    team_id,
    season,
):
    """
    Return exact normalized-name -> NBA player rows.

    Roster lookup is preferred over nba_api static metadata
    because preseason rosters include very recent players.
    """

    lookup = {}

    try:
        roster = (
            commonteamroster
            .CommonTeamRoster(
                team_id=int(
                    team_id
                ),
                season=str(
                    season
                ),
                timeout=30,
            )
            .get_data_frames()[0]
        )

    except Exception:
        return lookup

    for _, row in roster.iterrows():
        name = normalize_name(
            row.get(
                "PLAYER",
                "",
            )
        )

        if not name:
            continue

        lookup.setdefault(
            name,
            [],
        ).append(
            {
                "id":
                    int(
                        row[
                            "PLAYER_ID"
                        ]
                    ),

                "name":
                    str(
                        row[
                            "PLAYER"
                        ]
                    ),
            }
        )

    return lookup


def resolve_nba_person_id(
    player_name,
    team_id,
    season,
):
    normalized = normalize_name(
        player_name
    )

    if not normalized:
        return None

    roster_matches = (
        current_roster_name_map(
            int(
                team_id
            ),
            str(
                season
            ),
        )
        .get(
            normalized,
            [],
        )
    )

    if len(
        roster_matches
    ) == 1:
        return int(
            roster_matches[0][
                "id"
            ]
        )

    if len(
        roster_matches
    ) > 1:
        return None

    static_matches = (
        static_player_name_map()
        .get(
            normalized,
            [],
        )
    )

    if len(
        static_matches
    ) == 1:
        return int(
            static_matches[0][
                "id"
            ]
        )

    return None


@lru_cache(maxsize=64)
def resolve_nba_game_metadata(
    canonical_game_id,
    formatted_date,
):
    games = (
        fetch_games_for_date_from_scoreboard(
            formatted_date,
            timeout=30,
        )
    )

    for game in games:
        if (
            str(
                game[
                    "game_id"
                ]
            ).zfill(
                10
            )
            ==
            str(
                canonical_game_id
            ).zfill(
                10
            )
        ):
            return game

    raise ESPNLiveFeedError(
        "Could not resolve NBA game metadata "
        f"for {canonical_game_id} on "
        f"{formatted_date}."
    )


def fetch_espn_scoreboard(
    game_date,
    timeout=15,
):
    date_key = (
        pd.Timestamp(
            game_date
        )
        .strftime(
            "%Y%m%d"
        )
    )

    response = requests.get(
        ESPN_SCOREBOARD_URL,
        params={
            "dates":
                date_key,

            "limit":
                100,
        },
        timeout=timeout,
    )

    response.raise_for_status()

    return response.json()


def event_competitors(
    event,
):
    competitions = event.get(
        "competitions",
        [],
    )

    if not competitions:
        return {}

    competitors = (
        competitions[0]
        .get(
            "competitors",
            [],
        )
    )

    result = {}

    for competitor in competitors:
        side = competitor.get(
            "homeAway"
        )

        team = competitor.get(
            "team",
            {},
        )

        if side not in (
            "home",
            "away",
        ):
            continue

        result[
            side
        ] = {
            "espn_team_id":
                str(
                    team.get(
                        "id",
                        "",
                    )
                ),

            "display_name":
                str(
                    team.get(
                        "displayName",
                        "",
                    )
                ),

            "abbreviation":
                str(
                    team.get(
                        "abbreviation",
                        "",
                    )
                ),
        }

    return result


def resolve_espn_event(
    canonical_game_id,
    game_date,
    timeout=15,
):
    formatted_date = (
        pd.Timestamp(
            game_date
        )
        .strftime(
            "%Y-%m-%d"
        )
    )

    nba_game = (
        resolve_nba_game_metadata(
            str(
                canonical_game_id
            ).zfill(
                10
            ),
            formatted_date,
        )
    )

    home_team_id = int(
        nba_game[
            "home_team_id"
        ]
    )

    away_team_id = int(
        nba_game[
            "away_team_id"
        ]
    )

    home_team = (
        _NBA_TEAMS_BY_ID.get(
            home_team_id
        )
    )

    away_team = (
        _NBA_TEAMS_BY_ID.get(
            away_team_id
        )
    )

    if (
        home_team is None
        or away_team is None
    ):
        raise ESPNLiveFeedError(
            "Could not resolve NBA team names "
            f"for game {canonical_game_id}."
        )

    expected_home = normalize_name(
        home_team[
            "full_name"
        ]
    )

    expected_away = normalize_name(
        away_team[
            "full_name"
        ]
    )

    scoreboard = (
        fetch_espn_scoreboard(
            formatted_date,
            timeout=timeout,
        )
    )

    for event in scoreboard.get(
        "events",
        [],
    ):
        competitors = (
            event_competitors(
                event
            )
        )

        home = competitors.get(
            "home"
        )

        away = competitors.get(
            "away"
        )

        if (
            home is None
            or away is None
        ):
            continue

        if (
            normalize_name(
                home[
                    "display_name"
                ]
            )
            != expected_home
        ):
            continue

        if (
            normalize_name(
                away[
                    "display_name"
                ]
            )
            != expected_away
        ):
            continue

        team_map = {
            str(
                home[
                    "espn_team_id"
                ]
            ):
                {
                    "team_id":
                        home_team_id,

                    "team_tricode":
                        nba_game[
                            "home_tricode"
                        ],

                    "side":
                        "home",
                },

            str(
                away[
                    "espn_team_id"
                ]
            ):
                {
                    "team_id":
                        away_team_id,

                    "team_tricode":
                        nba_game[
                            "away_tricode"
                        ],

                    "side":
                        "away",
                },
        }

        return {
            "event_id":
                str(
                    event[
                        "id"
                    ]
                ),

            "nba_game":
                nba_game,

            "team_map":
                team_map,
        }

    raise ESPNLiveFeedError(
        "Could not match NBA game "
        f"{canonical_game_id} to an ESPN event "
        f"on {formatted_date}."
    )


def fetch_espn_summary(
    event_id,
    timeout=15,
):
    response = requests.get(
        ESPN_SUMMARY_URL,
        params={
            "event":
                str(
                    event_id
                ),
        },
        timeout=timeout,
    )

    response.raise_for_status()

    payload = response.json()

    if not payload:
        raise ESPNLiveFeedError(
            "ESPN summary returned no data "
            f"for event {event_id}."
        )

    return payload


def build_espn_player_maps(
    summary,
    team_map,
    season,
):
    """
    Build two mappings:

    ESPN athlete ID -> canonical NBA player metadata.
    (ESPN team ID, normalized player name) -> NBA person ID.
    """

    athletes = {}

    names = {}

    player_groups = (
        summary
        .get(
            "boxscore",
            {},
        )
        .get(
            "players",
            [],
        )
    )

    for group in player_groups:
        espn_team_id = str(
            group
            .get(
                "team",
                {},
            )
            .get(
                "id",
                "",
            )
        )

        canonical_team = (
            team_map.get(
                espn_team_id
            )
        )

        if canonical_team is None:
            continue

        nba_team_id = int(
            canonical_team[
                "team_id"
            ]
        )

        for statistics in group.get(
            "statistics",
            [],
        ):
            for athlete_row in statistics.get(
                "athletes",
                [],
            ):
                athlete = athlete_row.get(
                    "athlete",
                    {},
                )

                espn_player_id = str(
                    athlete.get(
                        "id",
                        "",
                    )
                )

                player_name = (
                    athlete.get(
                        "displayName"
                    )
                    or athlete.get(
                        "fullName"
                    )
                    or athlete.get(
                        "shortName"
                    )
                    or ""
                )

                if (
                    not espn_player_id
                    or not player_name
                ):
                    continue

                nba_person_id = (
                    resolve_nba_person_id(
                        player_name,
                        nba_team_id,
                        season,
                    )
                )

                metadata = {
                    "espn_player_id":
                        espn_player_id,

                    "player_name":
                        str(
                            player_name
                        ),

                    "nba_person_id":
                        nba_person_id,

                    "nba_team_id":
                        nba_team_id,

                    "team_tricode":
                        canonical_team[
                            "team_tricode"
                        ],
                }

                athletes[
                    espn_player_id
                ] = metadata

                names[
                    (
                        espn_team_id,
                        normalize_name(
                            player_name
                        ),
                    )
                ] = metadata

    return (
        athletes,
        names,
    )


def normalize_clock(
    value,
):
    value = str(
        value
        or ""
    ).strip()

    minute_match = re.fullmatch(
        r"(\d+):(\d+(?:\.\d+)?)",
        value,
    )

    seconds_match = re.fullmatch(
        r"(\d+(?:\.\d+)?)",
        value,
    )

    if minute_match is not None:
        minutes = int(
            minute_match.group(
                1
            )
        )

        seconds = float(
            minute_match.group(
                2
            )
        )

    elif seconds_match is not None:
        minutes = 0

        seconds = float(
            seconds_match.group(
                1
            )
        )

    else:
        raise ESPNLiveFeedError(
            "Unexpected ESPN clock format: "
            f"{value!r}"
        )

    seconds_text = (
        f"{seconds:.2f}"
        .rstrip(
            "0"
        )
        .rstrip(
            "."
        )
    )

    return (
        f"PT{minutes}M"
        f"{seconds_text}S"
    )


def safe_int(
    value,
    default=0,
):
    try:
        return int(
            float(
                value
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        return int(
            default
        )


def normalize_action_type(
    play,
):
    type_text = str(
        play
        .get(
            "type",
            {},
        )
        .get(
            "text",
            "",
        )
    ).strip()

    short_description = str(
        play.get(
            "shortDescription",
            "",
        )
    ).strip()

    lowered = (
        f"{type_text} "
        f"{short_description}"
    ).lower()

    if "free throw" in lowered:
        return "Free Throw"

    if "substitution" in lowered:
        return "Substitution"

    if "rebound" in lowered:
        return "Rebound"

    if (
        "turnover" in lowered
        or type_text.lower()
        == "traveling"
    ):
        return "Turnover"

    if bool(
        play.get(
            "scoringPlay"
        )
    ) and safe_int(
        play.get(
            "scoreValue"
        )
    ) > 0:
        return "Made Shot"

    if bool(
        play.get(
            "shootingPlay"
        )
    ):
        return "Missed Shot"

    if "foul" in lowered:
        return "Foul"

    if "timeout" in lowered:
        return "Timeout"

    if (
        "jumpball"
        in lowered
        or "jump ball"
        in lowered
    ):
        return "Jump Ball"

    if "end period" in lowered:
        return "Period"

    if "end game" in lowered:
        return "Game"

    return (
        type_text
        or short_description
        or "Other"
    )


def normalize_sub_type(
    play,
    action_type,
):
    type_text = str(
        play
        .get(
            "type",
            {},
        )
        .get(
            "text",
            "",
        )
    ).strip()

    if (
        action_type
        == "Free Throw"
    ):
        match = re.search(
            r"Free Throw\s*-\s*(.+)$",
            type_text,
            flags=re.IGNORECASE,
        )

        if match is not None:
            return (
                match.group(
                    1
                )
                .strip()
            )

    return type_text


def player_initial_name(
    player_name,
):
    parts = str(
        player_name
        or ""
    ).split()

    if len(
        parts
    ) < 2:
        return str(
            player_name
            or ""
        )

    return (
        f"{parts[0][0]}. "
        f"{' '.join(parts[1:])}"
    )


def normalize_espn_play(
    play,
    row_number,
    team_map,
    athlete_map,
    name_map,
):
    action_type = (
        normalize_action_type(
            play
        )
    )

    espn_team_id = str(
        play
        .get(
            "team",
            {},
        )
        .get(
            "id",
            "",
        )
    )

    canonical_team = (
        team_map.get(
            espn_team_id
        )
    )

    if canonical_team is None:
        team_id = 0
        team_tricode = ""

    else:
        team_id = int(
            canonical_team[
                "team_id"
            ]
        )

        team_tricode = str(
            canonical_team[
                "team_tricode"
            ]
        )

    description = str(
        play.get(
            "text",
            "",
        )
        or ""
    )

    person_id = 0
    player_name = ""

    participants = play.get(
        "participants",
        [],
    )

    if participants:
        espn_player_id = str(
            participants[0]
            .get(
                "athlete",
                {},
            )
            .get(
                "id",
                "",
            )
        )

        player = athlete_map.get(
            espn_player_id
        )

        if player is not None:
            player_name = str(
                player[
                    "player_name"
                ]
            )

            if (
                player[
                    "nba_person_id"
                ]
                is not None
            ):
                person_id = int(
                    player[
                        "nba_person_id"
                    ]
                )

    if (
        action_type
        == "Substitution"
    ):
        match = re.match(
            (
                r"^(.+?)\s+"
                r"enters the game for\s+"
                r"(.+?)$"
            ),
            description.strip(),
            flags=re.IGNORECASE,
        )

        if match is not None:
            incoming_name = (
                match.group(
                    1
                )
                .strip()
            )

            outgoing_name = (
                match.group(
                    2
                )
                .strip()
            )

            description = (
                f"SUB: "
                f"{incoming_name} "
                f"FOR "
                f"{outgoing_name}"
            )

            player_name = (
                outgoing_name
            )

            outgoing_player = (
                name_map.get(
                    (
                        espn_team_id,
                        normalize_name(
                            outgoing_name
                        ),
                    )
                )
            )

            if (
                outgoing_player
                is not None
                and outgoing_player[
                    "nba_person_id"
                ]
                is not None
            ):
                person_id = int(
                    outgoing_player[
                        "nba_person_id"
                    ]
                )

            else:
                person_id = 0

    espn_sequence_number = safe_int(
        play.get(
            "sequenceNumber"
        ),
        default=row_number,
    )

    period = safe_int(
        play
        .get(
            "period",
            {},
        )
        .get(
            "number"
        )
    )

    clock = normalize_clock(
        play
        .get(
            "clock",
            {},
        )
        .get(
            "displayValue",
            "",
        )
    )

    return {
        "actionId":
            int(
                row_number
            ),

        "actionNumber":
            int(
                row_number
            ),

        "period":
            period,

        "clock":
            clock,

        "teamId":
            team_id,

        "teamTricode":
            team_tricode,

        "personId":
            person_id,

        "playerName":
            player_name,

        "playerNameI":
            player_initial_name(
                player_name
            ),

        "actionType":
            action_type,

        "subType":
            normalize_sub_type(
                play,
                action_type,
            ),

        "description":
            description,

        "scoreHome":
            safe_int(
                play.get(
                    "homeScore"
                )
            ),

        "scoreAway":
            safe_int(
                play.get(
                    "awayScore"
                )
            ),

        "espnPlayId":
            str(
                play.get(
                    "id",
                    "",
                )
            ),

        "espnSequenceNumber":
            espn_sequence_number,

        "wallclock":
            str(
                play.get(
                    "wallclock",
                    "",
                )
            ),
    }


def fetch_espn_live_play_by_play(
    game_id,
    game_date,
    season,
    timeout=15,
):
    canonical_game_id = str(
        game_id
    ).zfill(
        10
    )

    try:
        resolved = (
            resolve_espn_event(
                canonical_game_id,
                game_date,
                timeout=timeout,
            )
        )

        summary = (
            fetch_espn_summary(
                resolved[
                    "event_id"
                ],
                timeout=timeout,
            )
        )

        plays = summary.get(
            "plays",
            [],
        )

        if not plays:
            raise ESPNLiveFeedError(
                "ESPN has not returned any "
                "play-by-play events yet for "
                f"{canonical_game_id}."
            )

        (
            athlete_map,
            name_map,
        ) = build_espn_player_maps(
            summary,
            resolved[
                "team_map"
            ],
            season,
        )

        rows = [
            normalize_espn_play(
                play,
                row_number=index + 1,
                team_map=resolved[
                    "team_map"
                ],
                athlete_map=(
                    athlete_map
                ),
                name_map=(
                    name_map
                ),
            )
            for index, play
            in enumerate(
                plays
            )
        ]

        df = (
            pd.DataFrame(
                rows
            )
            .reset_index(
                drop=True
            )
        )

        if df.empty:
            raise ESPNLiveFeedError(
                "ESPN play-by-play normalized "
                "to an empty dataframe for "
                f"{canonical_game_id}."
            )

        df.attrs[
            "courtvision_pbp_source"
        ] = "espn"

        df.attrs[
            "espn_event_id"
        ] = resolved[
            "event_id"
        ]

        return df

    except ESPNLiveFeedError:
        raise

    except Exception as error:
        raise ESPNLiveFeedError(
            "ESPN live play-by-play failed "
            f"for {canonical_game_id}: "
            f"{error}"
        ) from error
