import html
import pandas as pd
import numpy as np
import sys

from datetime import date
from nba_api.stats.static import players as nba_players
from pathlib import Path



import plotly.graph_objects as go

import json
import os
import pickle
import subprocess
import streamlit as st
from nba_api.stats.endpoints import commonteamroster, commonplayerinfo




# ============================================================

# Project path

# ============================================================



ROOT_DIR = (

    Path(__file__)

    .resolve()

    .parents[1]

)



SRC_DIR = (

    ROOT_DIR

    / "src"

)



if str(SRC_DIR) not in sys.path:

    sys.path.append(

        str(SRC_DIR)

    )





# ============================================================

# Project imports

# ============================================================



from analysis import (

    analyze_game,

)



from momentum import detect_momentum_runs
from contextual_explanations import build_contextual_explanations
from game_story import build_game_story


from box_score import (
    fetch_box_score,
    get_team_players,
)


from game_catalog import (

    fetch_season_games,
    games_for_date_from_season_df,

)



from live_analysis import (

    analyze_live_game,

)



from player_impact import (

    analyze_player_impact,

)



from predict_game import (

    add_play_by_play_details,

    format_clock,

)



from team_metadata import (

    TEAM_METADATA,

    get_team_metadata,

)





# ============================================================

# Page

# ============================================================



st.set_page_config(

    page_title="Courtvision",

    page_icon="🏀",

    layout="wide",

)





# ============================================================

# Seasons

# ============================================================



EARLIEST_SEASON_START = 2019

LATEST_SEASON_START = 2026



AVAILABLE_SEASONS = [

    (

        f"{year}-"

        f"{str(year + 1)[-2:]}"

    )

    for year in range(

        LATEST_SEASON_START,

        EARLIEST_SEASON_START - 1,

        -1,

    )

]





def default_date_for_season(

    season,

):

    start_year = int(

        season.split(

            "-"

        )[0]

    )



    if season == "2026-27":

        return date.today()



    return date(

        start_year + 1,

        1,

        15,

    )





# ============================================================

# Styling

# ============================================================



st.markdown(

    """

    <style>



    .courtvision-team {

        text-align: center;

        padding-top: 0.25rem;

    }



    .courtvision-team-code {

        font-size: 1.35rem;

        font-weight: 750;

        margin-top: 0.15rem;

    }



    .courtvision-score {

        font-size: 3.25rem;

        font-weight: 750;

        line-height: 1;

        margin-top: 0.35rem;

        margin-bottom: 0.35rem;

    }



    .courtvision-team-name {

        font-size: 0.95rem;

        opacity: 0.75;

        margin-top: 0.15rem;

    }



    .courtvision-record {

        font-size: 0.9rem;

        opacity: 0.62;

        margin-top: 0.35rem;

    }



    .courtvision-status {

        text-align: center;

        font-size: 1rem;

        font-weight: 750;

        letter-spacing: 0.06em;

        opacity: 0.75;

        padding-top: 3.2rem;

    }



    .live-indicator {

        display: inline-block;

        border:

            1px solid

            rgba(255,255,255,0.18);

        border-radius: 999px;

        padding: 0.28rem 0.75rem;

        font-size: 0.78rem;

        font-weight: 700;

        letter-spacing: 0.06em;

        margin-bottom: 0.6rem;

    }



    .turning-point-card {

        border:

            1px solid

            rgba(255,255,255,0.10);

        border-left-width: 4px;

        border-radius: 10px;

        padding: 1rem 1rem 0.9rem 1rem;

        margin-bottom: 0.85rem;

        background:

            rgba(255,255,255,0.025);

    }



    .turning-point-change {

        font-size: 1.15rem;

        font-weight: 750;

        margin-bottom: 0.3rem;

    }



    .turning-point-clock {

        font-size: 0.88rem;

        opacity: 0.72;

        margin-bottom: 0.65rem;

    }



    .turning-point-description {

        font-size: 0.95rem;

        line-height: 1.45;

        margin-bottom: 0.6rem;

    }



    .turning-point-probability {

        font-size: 0.85rem;

        opacity: 0.60;

    }



    </style>

    """,

    unsafe_allow_html=True,

)





# ============================================================

# Header

# ============================================================



st.title(

    "🏀 Courtvision"

)



st.caption(

    "NBA win probability "

    "and turning-point analysis"

)





# ============================================================

# Cached calendar lookup

# ============================================================



@st.cache_data(
    ttl=3600,
    show_spinner=False,
)
def cached_season_game_log(
    season,
):
    return (
        fetch_season_games(
            season=season,
            timeout=60,
        )
    )


def cached_games_for_date(
    season,
    selected_date,
):
    season_df = (
        cached_season_game_log(
            season
        )
    )

    return (
        games_for_date_from_season_df(
            season_df=season_df,
            game_date=selected_date,
        )
    )


@st.cache_data(
    show_spinner=False,
)
def get_player_name_lookup():
    return {
        int(player["id"]): player["full_name"]
        for player in nba_players.get_players()
    }


def get_full_player_name(row):
    fallback_name = str(
        row.get(
            "playerName",
            "Unknown",
        )
    )

    person_id = row.get(
        "personId"
    )

    if person_id is None:
        return fallback_name

    try:
        person_id = int(
            float(
                person_id
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        return fallback_name

    lookup = (
        get_player_name_lookup()
    )

    return lookup.get(
        person_id,
        fallback_name,
    )


def cached_existing_player_summary(
    game_id,
):
    """
    Load an already-computed WPA v3 summary from disk and
    normalize it to the column schema used by the dashboard.
    """

    result_path = (
        ROOT_DIR
        / "results"
        / f"player_wpa_v3_{game_id}_summary.csv"
    )

    if not result_path.exists():
        return None

    try:
        summary = pd.read_csv(
            result_path
        )

    except Exception:
        return None

    # --------------------------------------------------------
    # Saved player_impact.py output uses names such as:
    #
    #   playerName
    #   teamTricode
    #   netWPAPoints
    #
    # The dashboard/shared-attribution presentation uses:
    #
    #   player
    #   team
    #   net_wpa_pp
    #
    # Normalize either representation into one dashboard
    # contract here.
    # --------------------------------------------------------

    rename_map = {
        "playerName":
            "player",

        "teamTricode":
            "team",

        "netWPAPoints":
            "net_wpa_pp",

        "positiveWPAPoints":
            "positive_wpa_pp",

        "negativeWPAPoints":
            "negative_wpa_pp",

        "absoluteWPAPoints":
            "absolute_wpa_pp",

        "maxPositiveEventPoints":
            "max_positive_event_pp",

        "maxNegativeEventPoints":
            "max_negative_event_pp",
    }

    summary = summary.copy()

    # Preserve the canonical player-impact columns because
    # existing dashboard helpers still use them. Add aliases
    # instead of destructively renaming columns.
    for old, new in rename_map.items():
        if (
            old in summary.columns
            and new not in summary.columns
        ):
            summary[
                new
            ] = summary[
                old
            ]

    required = {
        "player",
        "team",
        "net_wpa_pp",
    }

    if not required.issubset(
        summary.columns
    ):
        return None

    numeric_columns = [
        "net_wpa_pp",
        "positive_wpa_pp",
        "negative_wpa_pp",
        "absolute_wpa_pp",
        "max_positive_event_pp",
        "max_negative_event_pp",
        "events",
    ]

    for column in numeric_columns:
        if column in summary.columns:
            summary[
                column
            ] = pd.to_numeric(
                summary[
                    column
                ],
                errors="coerce",
            )

    return summary



def cached_player_impact(

    game_id,

    season,

    attribution_version="v3",

):

    # Keep the attribution version in the cache key so
    # future assist/shared-credit changes cannot reuse
    # stale WPA output.

    del attribution_version



    return analyze_player_impact(

        game_id=game_id,

        season=season,

        top_k=10,

    )





# ============================================================

# Sidebar

# ============================================================



st.sidebar.header(

    "Navigation"

)





mode = st.sidebar.radio(

    "Mode",

    [

        "Historical",

        "Live",

        "Season Intelligence",

    ],

    key="courtvision_mode",

)





# ============================================================

# Historical mode

# ============================================================



if mode == "Historical":



    HISTORICAL_SEASONS = [

        "2025-26",

        "2024-25",

        "2023-24",

        "2022-23",

        "2021-22",

        "2020-21",

        "2019-20",

    ]





    # --------------------------------------------------------

    # Season selector

    # --------------------------------------------------------



    season = st.sidebar.selectbox(

        "Season",

        HISTORICAL_SEASONS,

        index=0,

        key="courtvision_historical_season",

    )





    # --------------------------------------------------------

    # Reset the calendar when season changes

    # --------------------------------------------------------



    previous_season = (

        st.session_state.get(

            "courtvision_previous_historical_season"

        )

    )



    if (

        previous_season

        != season

    ):

        start_year = int(

            season.split(

                "-"

            )[0]

        )



        # January is safely inside essentially

        # every NBA regular season.

        st.session_state[

            "courtvision_historical_date"

        ] = date(

            start_year + 1,

            1,

            15,

        )



        st.session_state[

            "courtvision_previous_historical_season"

        ] = season





    # --------------------------------------------------------

    # Calendar

    # --------------------------------------------------------



    selected_date = st.sidebar.date_input(

        "Date",

        key="courtvision_historical_date",

        format="MM/DD/YYYY",

    )





    # --------------------------------------------------------

    # Games for selected day

    # --------------------------------------------------------



    try:

        games = cached_games_for_date(

            season,

            selected_date,

        )



    except Exception as error:

        games = []



        st.sidebar.error(

            "Could not load games "

            f"for this date: {error}"

        )





    selected_game_id = None





    if games:

        st.sidebar.caption(

            (

                f"{len(games)} game"

                f"{'s' if len(games) != 1 else ''} "

                "on this date"

            )

        )



        labels = [

            game["label"]

            for game in games

        ]



        selected_label = st.sidebar.radio(

            "Game",

            labels,

            key="courtvision_historical_game",

        )



        selected_game = next(

            game

            for game in games

            if game["label"]

            == selected_label

        )



        selected_game_id = (

            selected_game[

                "game_id"

            ]

        )



    else:

        st.sidebar.info(

            "No regular-season games "

            "found on this date."

        )





    auto_refresh = False

    refresh_seconds = 15





# ============================================================

# Live mode

# ============================================================



elif mode == "Live":



    # --------------------------------------------------------

    # Live mode is CURRENT season only.

    # --------------------------------------------------------



    season = "2026-27"



    st.sidebar.caption(

        f"Current season: {season}"

    )





    # --------------------------------------------------------

    # Live mode always represents today's games.

    # --------------------------------------------------------



    selected_date = date.today()



    st.sidebar.caption(

        (

            "Today: "

            f"{selected_date.strftime('%B %d, %Y')}"

        )

    )





    # --------------------------------------------------------

    # Today's games

    # --------------------------------------------------------



    try:

        games = cached_games_for_date(

            season,

            selected_date,

        )



    except Exception as error:

        games = []



        st.sidebar.error(

            "Could not load today's games: "

            f"{error}"

        )





    selected_game_id = None





    if games:

        st.sidebar.caption(

            (

                f"{len(games)} game"

                f"{'s' if len(games) != 1 else ''} "

                "today"

            )

        )



        labels = [

            game["label"]

            for game in games

        ]



        selected_label = st.sidebar.radio(

            "Today's Games",

            labels,

            key="courtvision_live_game",

        )



        selected_game = next(

            game

            for game in games

            if game["label"]

            == selected_label

        )



        selected_game_id = (

            selected_game[

                "game_id"

            ]

        )



    else:

        st.sidebar.info(

            "No NBA games found today."

        )





    # --------------------------------------------------------

    # Optional fallback while developing

    # --------------------------------------------------------



    with st.sidebar.expander(

        "Developer Game ID"

    ):

        manual_game_id = (

            st.text_input(

                "Game ID",

                value="",

                key="courtvision_live_manual_game",

            )

        )



        if manual_game_id:

            selected_game_id = (

                manual_game_id

            )





    # --------------------------------------------------------

    # Refresh controls

    # --------------------------------------------------------



    auto_refresh = st.sidebar.toggle(

        "Auto refresh",

        value=True,

        key="courtvision_auto_refresh",

    )



    refresh_seconds = (

        st.sidebar.selectbox(

            "Refresh interval",

            [

                10,

                15,

                30,

                60,

            ],

            index=1,

            key="courtvision_refresh_interval",

        )

    )





# ============================================================

# Season Intelligence mode

# ============================================================



else:

    season_intelligence_dir = (
        ROOT_DIR
        / "results"
        / "season_intelligence"
    )

    SEASON_INTELLIGENCE_SEASONS = sorted(
        [
            path.name.replace(
                "_team_summary_v1.csv",
                "",
            )
            for path in (
                season_intelligence_dir.glob(
                    "*_team_summary_v1.csv"
                )
            )
            if (
                season_intelligence_dir
                / path.name.replace(
                    "_team_summary_v1.csv",
                    "_team_rating_games_v1.csv",
                )
            ).exists()
        ],
        reverse=True,
    )

    if not SEASON_INTELLIGENCE_SEASONS:
        raise RuntimeError(
            "No completed Season Intelligence seasons found."
        )



    season = st.sidebar.selectbox(

        "Season",

        SEASON_INTELLIGENCE_SEASONS,

        index=0,

        key="courtvision_season_intelligence_season",

    )



    st.sidebar.caption(

        "Frozen Team Courtvision Rating v1"

    )



    selected_game_id = None

    selected_date = None

    auto_refresh = False

    refresh_seconds = 15





# ============================================================

# Analyze button

# ============================================================



if mode != "Season Intelligence":

    analyze_button = st.sidebar.button(

        "Analyze Game",

        type="primary",

        disabled=(

            selected_game_id

            is None

        ),

        key="courtvision_analyze_game",

    )



else:

    analyze_button = False





# ============================================================

# Session state

# ============================================================



if (

    "courtvision_active"

    not in st.session_state

):

    st.session_state[

        "courtvision_active"

    ] = False





if analyze_button:

    st.session_state[

        "courtvision_active"

    ] = True



current_mode = (

    st.session_state.get(

        "courtvision_last_mode"

    )

)



if current_mode != mode:

    st.session_state[

        "courtvision_active"

    ] = False



    st.session_state[

        "courtvision_last_mode"

    ] = mode





# ============================================================

# Helpers

# ============================================================



def format_pregame_record(

    wins,

    losses,

):

    return (

        f"{wins}-{losses}"

    )





def render_team_logo(

    team,

    width=108,

):

    logo = (

        team.get(

            "logo"

        )

    )



    if (

        logo is not None

        and Path(

            logo

        ).exists()

    ):

        left, center, right = (

            st.columns(

                [1, 1, 1]

            )

        )



        with center:

            st.image(

                logo,

                width=width,

            )





def normalize_clock_display(

    clock,

):

    if clock is None:

        return ""



    try:

        return format_clock(

            str(

                clock

            )

        )



    except Exception:

        return str(

            clock

        )





# ============================================================

# Chart

# ============================================================




def hex_to_rgb(
    color,
):
    """
    Convert #RRGGBB to an RGB tuple.
    """

    if not isinstance(
        color,
        str,
    ):
        return None

    color = (
        color.strip()
        .lstrip("#")
    )

    if len(color) != 6:
        return None

    try:
        return tuple(
            int(
                color[index:index + 2],
                16,
            )
            for index
            in (
                0,
                2,
                4,
            )
        )

    except ValueError:
        return None


def chart_color_distance(
    color_a,
    color_b,
):
    """
    Simple RGB distance used only to determine
    whether two matchup colors are visually
    difficult to distinguish.
    """

    rgb_a = (
        hex_to_rgb(
            color_a
        )
    )

    rgb_b = (
        hex_to_rgb(
            color_b
        )
    )

    if (
        rgb_a is None
        or rgb_b is None
    ):
        return 999.0

    return (
        sum(
            (
                component_a
                - component_b
            ) ** 2

            for (
                component_a,
                component_b,
            )
            in zip(
                rgb_a,
                rgb_b,
            )
        )
        ** 0.5
    )




def relative_luminance(
    color,
):
    """
    WCAG-style relative luminance for a hex color.
    """

    rgb = (
        hex_to_rgb(
            color
        )
    )

    if rgb is None:
        return 1.0

    channels = []

    for value in rgb:
        channel = (
            value / 255.0
        )

        if channel <= 0.04045:
            channel = (
                channel / 12.92
            )

        else:
            channel = (
                (
                    channel + 0.055
                )
                / 1.055
            ) ** 2.4

        channels.append(
            channel
        )

    return (
        0.2126
        * channels[0]
        + 0.7152
        * channels[1]
        + 0.0722
        * channels[2]
    )


def contrast_ratio(
    color_a,
    color_b,
):
    luminance_a = (
        relative_luminance(
            color_a
        )
    )

    luminance_b = (
        relative_luminance(
            color_b
        )
    )

    lighter = max(
        luminance_a,
        luminance_b,
    )

    darker = min(
        luminance_a,
        luminance_b,
    )

    return (
        (
            lighter + 0.05
        )
        / (
            darker + 0.05
        )
    )


def resolve_matchup_chart_styles(
    home_team,
    away_team,
):
    """
    Pick team-authentic colors that satisfy two goals:

    1. distinguish the two teams from each other;
    2. remain readable against Courtvision's dark background.

    Candidate order:
        chart color
        primary team color
        secondary team color
        optional chart alternate color

    If a team's normal secondary color is black, for example,
    it will be rejected on the dark dashboard.
    """

    background = (
        "#0E1117"
    )

    minimum_background_contrast = (
        2.2
    )

    minimum_team_distance = (
        95.0
    )

    def candidate_colors(
        team,
    ):
        values = [
            team.get(
                "chart_color"
            ),
            team.get(
                "primary_color"
            ),
            team.get(
                "secondary_color"
            ),
            team.get(
                "alternate_chart_color"
            ),
        ]

        result = []

        for value in values:
            if (
                value
                and value not in result
            ):
                result.append(
                    value
                )

        return result


    home_candidates = (
        candidate_colors(
            home_team
        )
    )

    away_candidates = (
        candidate_colors(
            away_team
        )
    )


    # --------------------------------------------------------
    # Only keep colors that are visible on the dashboard.
    # --------------------------------------------------------

    readable_home = [
        color
        for color
        in home_candidates
        if (
            contrast_ratio(
                color,
                background,
            )
            >= minimum_background_contrast
        )
    ]

    readable_away = [
        color
        for color
        in away_candidates
        if (
            contrast_ratio(
                color,
                background,
            )
            >= minimum_background_contrast
        )
    ]


    # Always retain at least the chart color as a fallback.
    if not readable_home:
        readable_home = [
            home_team.get(
                "chart_color",
                "#58A6FF",
            )
        ]

    if not readable_away:
        readable_away = [
            away_team.get(
                "chart_color",
                "#FF5C77",
            )
        ]


    # --------------------------------------------------------
    # Score every possible color pairing.
    #
    # The dominant criterion is team-to-team separation.
    # Background contrast provides a secondary preference.
    # --------------------------------------------------------

    best_pair = None
    best_score = None

    for home_color in (
        readable_home
    ):
        for away_color in (
            readable_away
        ):
            team_distance = (
                chart_color_distance(
                    home_color,
                    away_color,
                )
            )

            home_contrast = (
                contrast_ratio(
                    home_color,
                    background,
                )
            )

            away_contrast = (
                contrast_ratio(
                    away_color,
                    background,
                )
            )

            # Prefer pairs that clear our team-separation
            # threshold, but still rank all candidates.
            separation_bonus = (
                1000.0
                if (
                    team_distance
                    >= minimum_team_distance
                )
                else 0.0
            )

            score = (
                separation_bonus
                + team_distance
                + 10.0
                * min(
                    home_contrast,
                    away_contrast,
                )
            )

            if (
                best_score is None
                or score > best_score
            ):
                best_score = score

                best_pair = (
                    home_color,
                    away_color,
                )


    home_color, away_color = (
        best_pair
    )


    return {
        "home_color":
            home_color,

        "away_color":
            away_color,

        "home_dash":
            "solid",

        "away_dash":
            "solid",

        "home_marker":
            "circle",

        "away_marker":
            "circle",
    }




def format_period_label(
    period,
):
    """
    Convert NBA period numbers into basketball-friendly labels.

    1 -> Q1
    2 -> Q2
    3 -> Q3
    4 -> Q4
    5 -> OT
    6 -> 2OT
    7 -> 3OT
    ...
    """

    try:
        period = int(
            period
        )

    except (
        TypeError,
        ValueError,
    ):
        return str(
            period
        )

    if period <= 4:
        return (
            f"Q{period}"
        )

    overtime_number = (
        period - 4
    )

    if overtime_number == 1:
        return "OT"

    return (
        f"{overtime_number}OT"
    )



def build_game_time_ticks(
    max_period,
):
    """
    Build basketball-aware x-axis ticks from the
    actual number of periods played.

    Regulation:
        Start, Q2, Q3, Q4, End

    1 OT:
        Start, Q2, Q3, Q4, OT, End

    2 OT:
        Start, Q2, Q3, Q4, OT, 2OT, End

    Period number, rather than elapsed floating-point
    time, determines how many overtime periods occurred.
    """

    try:
        max_period = int(
            max_period
        )

    except (
        TypeError,
        ValueError,
    ):
        max_period = 4

    max_period = max(
        4,
        max_period,
    )

    tickvals = [
        0,
        720,
        1440,
        2160,
    ]

    ticktext = [
        "Start",
        "Q2",
        "Q3",
        "Q4",
    ]

    # Regulation
    if max_period == 4:
        tickvals.append(
            2880
        )

        ticktext.append(
            "End"
        )

        return (
            tickvals,
            ticktext,
        )

    # Overtime
    overtime_count = (
        max_period - 4
    )

    for overtime_number in range(
        1,
        overtime_count + 1,
    ):
        overtime_start = (
            2880
            + (
                overtime_number - 1
            )
            * 300
        )

        tickvals.append(
            overtime_start
        )

        if overtime_number == 1:
            ticktext.append(
                "OT"
            )
        else:
            ticktext.append(
                f"{overtime_number}OT"
            )

    # End of the final OT period.
    game_end = (
        2880
        + overtime_count
        * 300
    )

    tickvals.append(
        game_end
    )

    ticktext.append(
        "End"
    )

    return (
        tickvals,
        ticktext,
    )


def build_win_probability_plot(
    game_df,
    home_swings,
    away_swings,
    home_team,
    away_team,
):
    """
    Display both teams' modeled win probabilities.

    V7 still predicts home-team win probability.
    Away-team probability is derived as:

        P(away win) = 1 - P(home win)

    No model behavior is changed here.
    """

    matchup_styles = (
        resolve_matchup_chart_styles(
            home_team,
            away_team,
        )
    )

    home_color = (
        matchup_styles[
            "home_color"
        ]
    )

    away_color = (
        matchup_styles[
            "away_color"
        ]
    )

    background_color = (
        "#0E1117"
    )

    text_color = (
        "#F3F4F6"
    )

    muted_text = (
        "#9CA3AF"
    )

    reference_color = (
        "rgba(255,255,255,0.30)"
    )

    grid_color = (
        "rgba(255,255,255,0.08)"
    )

    if (
        "isTerminalState"
        in game_df.columns
    ):
        model_game_df = (
            game_df[
                game_df[
                    "isTerminalState"
                ]
                == False
            ]
            .copy()
        )

        terminal_df = (
            game_df[
                game_df[
                    "isTerminalState"
                ]
                == True
            ]
            .copy()
        )

    else:
        model_game_df = (
            game_df.copy()
        )

        terminal_df = (
            game_df.iloc[
                0:0
            ].copy()
        )

    model_game_df = (
        model_game_df
        .dropna(
            subset=[
                "elapsedGameTime",
                "winProbability",
            ]
        )
        .copy()
    )

    if model_game_df.empty:
        return go.Figure()

    model_game_df[
        "homeWinProbabilityPct"
    ] = (
        model_game_df[
            "winProbability"
        ]
        * 100.0
    )

    model_game_df[
        "awayWinProbabilityPct"
    ] = (
        100.0
        - model_game_df[
            "homeWinProbabilityPct"
        ]
    )

    # --------------------------------------------------------
    # Hover data
    # --------------------------------------------------------

    def clean_score_value(
        value,
    ):
        try:
            if value != value:
                return ""

            return str(
                int(
                    float(value)
                )
            )

        except (
            TypeError,
            ValueError,
        ):
            return str(
                value
            )

    if (
        "scoreHome"
        in model_game_df.columns
    ):
        home_scores = (
            model_game_df[
                "scoreHome"
            ]
            .apply(
                clean_score_value
            )
            .tolist()
        )

    else:
        home_scores = (
            [""]
            * len(
                model_game_df
            )
        )

    if (
        "scoreAway"
        in model_game_df.columns
    ):
        away_scores = (
            model_game_df[
                "scoreAway"
            ]
            .apply(
                clean_score_value
            )
            .tolist()
        )

    else:
        away_scores = (
            [""]
            * len(
                model_game_df
            )
        )

    home_customdata = list(
        zip(
            model_game_df[
                "awayWinProbabilityPct"
            ].tolist(),
            home_scores,
            away_scores,
        )
    )

    away_customdata = list(
        zip(
            model_game_df[
                "homeWinProbabilityPct"
            ].tolist(),
            home_scores,
            away_scores,
        )
    )

    fig = (
        go.Figure()
    )

    # --------------------------------------------------------
    # Home team
    # --------------------------------------------------------

    fig.add_trace(
        go.Scatter(
            x=(
                model_game_df[
                    "elapsedGameTime"
                ]
            ),

            y=(
                model_game_df[
                    "homeWinProbabilityPct"
                ]
            ),

            mode="lines",

            line={
                "color":
                    home_color,

                "width":
                    4,

                "dash":
                    matchup_styles[
                        "home_dash"
                    ],
            },

            name=(
                home_team[
                    "tricode"
                ]
            ),

            customdata=(
                home_customdata
            ),

            hovertemplate=(
                "<b>"
                f"{home_team['tricode']} "
                "%{y:.1f}%"
                "</b><br>"

                f"{away_team['tricode']} "
                "%{customdata[0]:.1f}%"
                "<br>"

                "Score: "
                f"{away_team['tricode']} "
                "%{customdata[2]}"
                " – "
                "%{customdata[1]} "
                f"{home_team['tricode']}"

                "<extra></extra>"
            ),
        )
    )

    # --------------------------------------------------------
    # Away team
    # --------------------------------------------------------

    fig.add_trace(
        go.Scatter(
            x=(
                model_game_df[
                    "elapsedGameTime"
                ]
            ),

            y=(
                model_game_df[
                    "awayWinProbabilityPct"
                ]
            ),

            mode="lines",

            line={
                "color":
                    away_color,

                "width":
                    4,

                "dash":
                    matchup_styles[
                        "away_dash"
                    ],
            },

            name=(
                away_team[
                    "tricode"
                ]
            ),

            customdata=(
                away_customdata
            ),

            hovertemplate=(
                "<b>"
                f"{away_team['tricode']} "
                "%{y:.1f}%"
                "</b><br>"

                f"{home_team['tricode']} "
                "%{customdata[0]:.1f}%"
                "<br>"

                "Score: "
                f"{away_team['tricode']} "
                "%{customdata[2]}"
                " – "
                "%{customdata[1]} "
                f"{home_team['tricode']}"

                "<extra></extra>"
            ),
        )
    )

    # --------------------------------------------------------
    # 50% reference
    # --------------------------------------------------------

    fig.add_hline(
        y=50,
        line_dash="dash",
        line_width=1.5,
        line_color=(
            reference_color
        ),
    )

    fig.add_annotation(
        x=0,
        y=50,
        text="50% · Toss-up",
        showarrow=False,
        xanchor="left",
        xshift=4,
        yshift=12,
        font={
            "color":
                muted_text,

            "size":
                11,
        },
    )

    # Quarter boundaries. Overtime boundaries are
    # added later once the final elapsed time is known.
    for boundary in [
        720,
        1440,
        2160,
    ]:
        fig.add_vline(
            x=boundary,
            line_dash="dot",
            line_width=1,
            line_color=(
                reference_color
            ),
        )

    # --------------------------------------------------------
    # Largest home-benefiting turning point
    # --------------------------------------------------------

    if not home_swings.empty:
        row = (
            home_swings.iloc[0]
        )

        magnitude = (
            abs(
                float(
                    row[
                        "probabilityChange"
                    ]
                )
            )
            * 100.0
        )

        clock = (
            normalize_clock_display(
                row.get(
                    "clock"
                )
            )
        )

        period_label = (
            format_period_label(
                row.get(
                    "period"
                )
            )
        )

        fig.add_trace(
            go.Scatter(
                x=[
                    row[
                        "elapsedGameTime"
                    ]
                ],

                y=[
                    float(
                        row[
                            "winProbability"
                        ]
                    )
                    * 100.0
                ],

                mode="markers",

                marker={
                    "size":
                        13,

                    "color":
                        home_color,

                    "symbol":
                        matchup_styles[
                            "home_marker"
                        ],

                    "line": {
                        "color":
                            "#FFFFFF",

                        "width":
                            2,
                    },
                },

                showlegend=False,

                hovertemplate=(
                    "<b>"
                    f"{home_team['tricode']} "
                    f"+{magnitude:.1f} pp"
                    "</b><br>"

                    f"{period_label} "
                    f"{clock}<br>"

                    f"{row.get('description', '')}"

                    "<extra></extra>"
                ),
            )
        )

    # --------------------------------------------------------
    # Largest away-benefiting turning point
    # --------------------------------------------------------

    if not away_swings.empty:
        row = (
            away_swings.iloc[0]
        )

        magnitude = (
            abs(
                float(
                    row[
                        "probabilityChange"
                    ]
                )
            )
            * 100.0
        )

        away_probability = (
            100.0
            - (
                float(
                    row[
                        "winProbability"
                    ]
                )
                * 100.0
            )
        )

        clock = (
            normalize_clock_display(
                row.get(
                    "clock"
                )
            )
        )

        period_label = (
            format_period_label(
                row.get(
                    "period"
                )
            )
        )

        fig.add_trace(
            go.Scatter(
                x=[
                    row[
                        "elapsedGameTime"
                    ]
                ],

                y=[
                    away_probability
                ],

                mode="markers",

                marker={
                    "size":
                        13,

                    "color":
                        away_color,

                    "symbol":
                        matchup_styles[
                            "away_marker"
                        ],

                    "line": {
                        "color":
                            "#FFFFFF",

                        "width":
                            2,
                    },
                },

                showlegend=False,

                hovertemplate=(
                    "<b>"
                    f"{away_team['tricode']} "
                    f"+{magnitude:.1f} pp"
                    "</b><br>"

                    f"{period_label} "
                    f"{clock}<br>"

                    f"{row.get('description', '')}"

                    "<extra></extra>"
                ),
            )
        )

    # --------------------------------------------------------
    # Terminal state
    # --------------------------------------------------------

    final_time = float(
        model_game_df[
            "elapsedGameTime"
        ].max()
    )

    if not terminal_df.empty:
        terminal_row = (
            terminal_df.iloc[-1]
        )

        final_time = float(
            terminal_row[
                "elapsedGameTime"
            ]
        )

        terminal_home = (
            float(
                terminal_row[
                    "winProbability"
                ]
            )
            * 100.0
        )

        terminal_away = (
            100.0
            - terminal_home
        )

        previous_row = (
            model_game_df.iloc[-1]
        )

        previous_time = (
            float(
                previous_row[
                    "elapsedGameTime"
                ]
            )
        )

        previous_home = (
            float(
                previous_row[
                    "winProbability"
                ]
            )
            * 100.0
        )

        previous_away = (
            100.0
            - previous_home
        )

        fig.add_trace(
            go.Scatter(
                x=[
                    previous_time,
                    final_time,
                ],

                y=[
                    previous_home,
                    terminal_home,
                ],

                mode="lines",

                line={
                    "color":
                        home_color,

                    "width":
                        2,

                    "dash":
                        "dot",
                },

                hoverinfo="skip",
                showlegend=False,
            )
        )

        fig.add_trace(
            go.Scatter(
                x=[
                    previous_time,
                    final_time,
                ],

                y=[
                    previous_away,
                    terminal_away,
                ],

                mode="lines",

                line={
                    "color":
                        away_color,

                    "width":
                        2,

                    "dash":
                        "dot",
                },

                hoverinfo="skip",
                showlegend=False,
            )
        )

    max_elapsed = max(
        2880.0,
        final_time,
    )

    # Use actual NBA period numbers to determine
    # regulation vs overtime. Do not infer overtime
    # count from floating-point elapsed time.
    period_values = []

    if (
        "period"
        in model_game_df.columns
    ):
        period_values.extend(
            model_game_df[
                "period"
            ]
            .dropna()
            .tolist()
        )

    if (
        not terminal_df.empty
        and "period"
        in terminal_df.columns
    ):
        period_values.extend(
            terminal_df[
                "period"
            ]
            .dropna()
            .tolist()
        )

    max_period = (
        int(
            max(
                period_values
            )
        )
        if period_values
        else 4
    )

    (
        time_tickvals,
        time_ticktext,
    ) = build_game_time_ticks(
        max_period
    )

    # Add only the overtime boundaries that actually
    # correspond to periods played.
    overtime_count = max(
        0,
        max_period - 4,
    )

    for overtime_index in range(
        overtime_count
    ):
        overtime_boundary = (
            2880.0
            + overtime_index
            * 300.0
        )

        fig.add_vline(
            x=(
                overtime_boundary
            ),
            line_dash="dot",
            line_width=1,
            line_color=(
                reference_color
            ),
        )

    # --------------------------------------------------------
    # Layout
    # --------------------------------------------------------

    fig.update_layout(
        title={
            "text": (
                "<b>Win Probability</b><br>"
                "<span style='font-size:13px'>"
                f"{away_team['tricode']} "
                "vs "
                f"{home_team['tricode']}"
                "</span>"
            ),

            "x":
                0.01,

            "xanchor":
                "left",

            "y":
                0.98,

            "yanchor":
                "top",
        },

        height=560,

        paper_bgcolor=(
            background_color
        ),

        plot_bgcolor=(
            background_color
        ),

        font={
            "color":
                text_color,

            "size":
                13,
        },

        margin={
            "l":
                75,

            "r":
                65,

            "t":
                150,

            "b":
                65,
        },

        hovermode=(
            "closest"
        ),

        legend={
            "orientation":
                "h",

            "x":
                0.0,

            "xanchor":
                "left",

            "y":
                1.10,

            "yanchor":
                "bottom",

            "bgcolor":
                "rgba(0,0,0,0)",
        },
    )

    fig.update_xaxes(
        range=[
            -40,
            max_elapsed + 40,
        ],

        tickvals=(
            time_tickvals
        ),

        ticktext=(
            time_ticktext
        ),

        showgrid=False,
        zeroline=False,
        fixedrange=True,
        automargin=True,
    )

    fig.update_yaxes(
        title={
            "text":
                "Win Probability"
        },

        range=[
            0,
            103,
        ],

        tickvals=[
            0,
            25,
            50,
            75,
            100,
        ],

        ticktext=[
            "0%",
            "25%",
            "50%",
            "75%",
            "100%",
        ],

        showgrid=True,

        gridcolor=(
            grid_color
        ),

        zeroline=False,
        fixedrange=True,
        automargin=True,
    )

    return fig


def render_swing_card(
    row,
    team,
    direction,
):
    """
    Always express a turning point from
    the benefiting team's perspective.
    """

    clock = (
        normalize_clock_display(
            row.get(
                "clock"
            )
        )
    )

    home_change = float(
        row[
            "probabilityChange"
        ]
    )

    home_before = float(
        row[
            "previousWinProbability"
        ]
    )

    home_after = float(
        row[
            "winProbability"
        ]
    )

    if direction == "home":
        before = (
            home_before
            * 100.0
        )

        after = (
            home_after
            * 100.0
        )

    else:
        before = (
            1.0
            - home_before
        ) * 100.0

        after = (
            1.0
            - home_after
        ) * 100.0

    magnitude = (
        abs(
            home_change
        )
        * 100.0
    )

    color = (
        team.get(
            "chart_color",
            "#9CA3AF",
        )
    )

    description = (
        html.escape(
            str(
                row.get(
                    "description",
                    "",
                )
            )
        )
    )

    team_tricode = (
        html.escape(
            str(
                team[
                    "tricode"
                ]
            )
        )
    )

    period_label = (
        format_period_label(
            row.get(
                "period"
            )
        )
    )

    card_html = (
        f'<div class="turning-point-card" '
        f'style="border-left-color:{color};">'

        f'<div class="turning-point-change" '
        f'style="color:{color};">'

        f'▲ {team_tricode} '
        f'+{magnitude:.1f} pp'

        f'</div>'

        f'<div class="turning-point-clock">'

        f'{period_label} '
        f'{clock}'

        f'</div>'

        f'<div class="turning-point-description">'

        f'{description}'

        f'</div>'

        f'<div class="turning-point-probability">'

        f'{team_tricode} win probability: '
        f'{before:.1f}% → {after:.1f}%'

        f'</div>'

        f'</div>'
    )

    st.markdown(
        card_html,
        unsafe_allow_html=True,
    )


def get_team_wpa_leaders(

    player_summary,

    team_tricode,

    n=3,

):

    team_df = (

        player_summary[

            player_summary[

                "teamTricode"

            ]

            == team_tricode

        ]

        .copy()

    )



    if team_df.empty:

        return (

            team_df,

            team_df,

        )



    highest = (

        team_df

        .nlargest(

            n,

            "netWPAPoints",

        )

        .reset_index(

            drop=True

        )

    )



    lowest = (

        team_df

        .nsmallest(

            n,

            "netWPAPoints",

        )

        .reset_index(

            drop=True

        )

    )



    return (

        highest,

        lowest,

    )





def render_wpa_list(

    df,

    team_color,

):

    if df.empty:

        st.caption(

            "No WPA data available."

        )

        return



    for _, row in (

        df.iterrows()

    ):

        value = float(

            row[

                "netWPAPoints"

            ]

        )



        name = html.escape(
            get_full_player_name(
                row
            )
        )



        if value > 0:

            value_text = (

                f"+{value:.1f} pp"

            )

        elif value < 0:

            value_text = (

                f"{value:.1f} pp"

            )

        else:

            value_text = "0.0 pp"



        st.markdown(

            f"""
            <div style="
                display:flex;
                justify-content:space-between;
                align-items:center;
                gap:1rem;
                padding:0.5rem 0;
                border-bottom:1px solid rgba(128,128,128,0.18);
            ">
                <span style="
                    font-weight:600;
                    overflow:hidden;
                    text-overflow:ellipsis;
                    white-space:nowrap;
                ">
                    {name}
                </span>
                <span style="
                    color:{team_color};
                    font-weight:750;
                    font-variant-numeric:tabular-nums;
                    white-space:nowrap;
                ">
                    {value_text}
                </span>
            </div>
            """,

            unsafe_allow_html=True,

        )






def player_impact_runtime_dir():
    return (
        ROOT_DIR
        / "results"
        / ".runtime"
        / "player_impact"
    )


def player_impact_status_path(
    game_id,
):
    return (
        player_impact_runtime_dir()
        / f"{game_id}.json"
    )


def player_impact_log_path(
    game_id,
):
    return (
        player_impact_runtime_dir()
        / f"{game_id}.log"
    )


def player_impact_summary_path(
    game_id,
):
    return (
        ROOT_DIR
        / "results"
        / (
            f"player_wpa_v3_"
            f"{game_id}_summary.csv"
        )
    )


def _process_is_alive(
    pid,
):
    try:
        pid = int(
            pid
        )

        os.kill(
            pid,
            0,
        )

        return True

    except (
        TypeError,
        ValueError,
        ProcessLookupError,
    ):
        return False

    except PermissionError:
        # The PID exists, even if we cannot signal it.
        return True


def player_impact_background_status(
    game_id,
):
    game_id = str(
        game_id
    )

    if player_impact_summary_path(
        game_id
    ).exists():
        return {
            "state":
                "completed",
        }

    path = (
        player_impact_status_path(
            game_id
        )
    )

    if not path.exists():
        return {
            "state":
                "missing",
        }

    try:
        status = json.loads(
            path.read_text()
        )

    except Exception:
        return {
            "state":
                "missing",
        }

    state = (
        status.get(
            "state"
        )
    )

    if state in {
        "launching",
        "queued",
        "running",
    }:
        pid = status.get(
            "pid"
        )

        # "launching" may briefly have no PID yet.
        if (
            state == "running"
            and pid is not None
            and not _process_is_alive(
                pid
            )
        ):
            return {
                **status,
                "state":
                    "failed",

                "error":
                    (
                        "The Player Impact worker "
                        "stopped before producing a result."
                    ),
            }

    return status


def player_impact_service_status_path():
    return (
        player_impact_runtime_dir()
        / "service.json"
    )


def player_impact_request_dir():
    return (
        player_impact_runtime_dir()
        / "requests"
    )


def ensure_player_impact_service():
    """
    Ensure exactly one long-lived WPA service is available.

    The service keeps Frozen V7 model artifacts and loaded
    season DataFrames resident across game requests.
    """

    runtime_dir = (
        player_impact_runtime_dir()
    )

    runtime_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    status_path = (
        player_impact_service_status_path()
    )

    if status_path.exists():
        try:
            status = json.loads(
                status_path.read_text()
            )

            pid = status.get(
                "pid"
            )

            if (
                pid is not None
                and _process_is_alive(
                    pid
                )
            ):
                return status

        except Exception:
            pass

    log_path = (
        runtime_dir
        / "service.log"
    )

    log_file = open(
        log_path,
        "a",
    )

    try:
        process = subprocess.Popen(
            [
                sys.executable,
                str(
                    ROOT_DIR
                    / "src"
                    / "run_player_impact_service.py"
                ),
            ],
            cwd=str(
                ROOT_DIR
            ),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    finally:
        log_file.close()

    # Record the PID immediately so rapid Streamlit reruns
    # do not launch duplicate persistent workers.
    status = {
        "state":
            "launching",

        "pid":
            process.pid,
    }

    temp = status_path.with_suffix(
        ".json.tmp"
    )

    temp.write_text(
        json.dumps(
            status,
            indent=2,
        )
    )

    temp.replace(
        status_path
    )

    return status


@st.cache_resource(
    show_spinner=False,
)
def warm_player_impact_service():
    """
    Start the persistent Player Impact service once per
    Streamlit process.

    This moves Python/model startup off the first WPA
    request while preserving the existing lazy request
    queue for individual games.
    """

    try:
        return (
            ensure_player_impact_service()
        )

    except Exception:
        # Player Impact is supplemental. A warm-start failure
        # must never prevent the main Courtvision dashboard
        # from loading.
        return None


# Proactively warm the persistent WPA backend.
warm_player_impact_service()


def launch_player_impact_background(
    game_id,
    season,
    force=False,
):
    game_id = str(
        game_id
    )

    if (
        player_impact_summary_path(
            game_id
        ).exists()
        and not force
    ):
        return {
            "state":
                "completed",
        }

    current = (
        player_impact_background_status(
            game_id
        )
    )

    if (
        not force
        and current.get(
            "state"
        )
        in {
            "launching",
            "queued",
            "running",
        }
    ):
        return current

    service = (
        ensure_player_impact_service()
    )

    service_pid = (
        service.get(
            "pid"
        )
    )

    request_dir = (
        player_impact_request_dir()
    )

    request_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    status_path = (
        player_impact_status_path(
            game_id
        )
    )

    status_payload = {
        "state":
            "queued",

        "pid":
            service_pid,

        "game_id":
            game_id,

        "season":
            season,
    }

    status_temp = (
        status_path.with_suffix(
            ".json.tmp"
        )
    )

    status_temp.write_text(
        json.dumps(
            status_payload,
            indent=2,
        )
    )

    status_temp.replace(
        status_path
    )

    request_path = (
        request_dir
        / f"{game_id}.json"
    )

    request_temp = (
        request_path.with_suffix(
            ".json.tmp"
        )
    )

    request_temp.write_text(
        json.dumps(
            {
                "game_id":
                    game_id,

                "season":
                    season,

                "top_k":
                    10,

                "force":
                    bool(
                        force
                    ),
            },
            indent=2,
        )
    )

    request_temp.replace(
        request_path
    )

    return status_payload



def render_player_impact_summary(
    summary,
    home_team,
    away_team,
    home_team_metadata,
    away_team_metadata,
):
    (
        home_high,
        home_low,
    ) = get_team_wpa_leaders(
        summary,
        home_team,
    )

    (
        away_high,
        away_low,
    ) = get_team_wpa_leaders(
        summary,
        away_team,
    )

    home_color = (
        home_team_metadata.get(
            "chart_color",
            "#58A6FF",
        )
    )

    away_color = (
        away_team_metadata.get(
            "chart_color",
            "#FF5C77",
        )
    )

    home_col, away_col = (
        st.columns(
            2
        )
    )

    with home_col:
        st.markdown(
            f"### {home_team}"
        )

        st.markdown(
            "**Highest WPA contributors**"
        )

        render_wpa_list(
            home_high,
            home_color,
        )

        st.markdown(
            "<div style='height:0.75rem'></div>",
            unsafe_allow_html=True,
        )

        st.markdown(
            "**Lowest WPA contributors**"
        )

        render_wpa_list(
            home_low,
            home_color,
        )

    with away_col:
        st.markdown(
            f"### {away_team}"
        )

        st.markdown(
            "**Highest WPA contributors**"
        )

        render_wpa_list(
            away_high,
            away_color,
        )

        st.markdown(
            "<div style='height:0.75rem'></div>",
            unsafe_allow_html=True,
        )

        st.markdown(
            "**Lowest WPA contributors**"
        )

        render_wpa_list(
            away_low,
            away_color,
        )


@st.fragment(
    run_every=0.5,
)
def poll_player_impact_background(
    game_id,
):
    """
    Poll only.

    Worker launch happens in the normal Streamlit render path so
    Player Impact cannot silently fail to start because of fragment
    execution behavior.
    """

    game_id = str(
        game_id
    )

    summary = (
        cached_existing_player_summary(
            game_id
        )
    )

    if summary is not None:
        # One full rerun is useful here: it removes the temporary
        # "analyzing" message and lets Game Story pick up its newly
        # available player-impact enrichment too.
        st.rerun()
        return

    status = (
        player_impact_background_status(
            game_id
        )
    )

    state = (
        status.get(
            "state"
        )
    )

    if state == "failed":
        st.warning(
            "Player Impact analysis did not complete."
        )

        error = (
            status.get(
                "error"
            )
        )

        if error:
            with st.expander(
                "Player impact details"
            ):
                st.code(
                    str(error)
                )


def render_player_impact(
    game_id,
    season,
    home_team_metadata,
    away_team_metadata,
    live=False,
):
    st.subheader(
        "Player Impact"
    )

    st.caption(
        "Counterfactual Win Probability Added (WPA v3) "
        "with shared credit for assists, steals, and blocks. "
        "Positive WPA means a player's attributed events "
        "increased their team's modeled chance of winning."
    )

    if live:
        st.info(
            "Player WPA is currently shown for completed "
            "historical games. Live WPA will be enabled once "
            "the live player-impact pipeline is validated."
        )
        return

    game_id = str(
        game_id
    )

    # --------------------------------------------------------
    # Fast path: result already exists.
    # --------------------------------------------------------

    summary = (
        cached_existing_player_summary(
            game_id
        )
    )

    if summary is not None:
        render_player_impact_summary(
            summary=summary,
            home_team=(
                home_team_metadata[
                    "tricode"
                ]
            ),
            away_team=(
                away_team_metadata[
                    "tricode"
                ]
            ),
            home_team_metadata=(
                home_team_metadata
            ),
            away_team_metadata=(
                away_team_metadata
            ),
        )

        return

    # --------------------------------------------------------
    # Launch path.
    #
    # This happens in the normal Streamlit script execution,
    # NOT inside a fragment. Popen() returns immediately, so
    # the expensive WPA work still occurs outside Streamlit.
    # --------------------------------------------------------

    status = (
        player_impact_background_status(
            game_id
        )
    )

    state = (
        status.get(
            "state"
        )
    )

    if state == "missing":
        try:
            status = (
                launch_player_impact_background(
                    game_id=game_id,
                    season=season,
                )
            )

            state = (
                status.get(
                    "state"
                )
            )

        except Exception as error:
            st.error(
                "Could not start Player Impact analysis."
            )

            with st.expander(
                "Player impact details"
            ):
                st.code(
                    str(error)
                )

            return

    if state in {
        "launching",
        "queued",
        "running",
    }:
        st.info(
            "Analyzing Player Impact in the background. "
            "The rest of Courtvision remains available while "
            "the calculation finishes."
        )

        poll_player_impact_background(
            game_id
        )

        return

    if state == "failed":
        st.warning(
            "Player Impact analysis did not complete."
        )

        error = (
            status.get(
                "error"
            )
        )

        if error:
            with st.expander(
                "Player impact details"
            ):
                st.code(
                    str(error)
                )

        if st.button(
            "Retry Player Impact",
            key=(
                f"courtvision_retry_player_impact_"
                f"{game_id}_{season}"
            ),
        ):
            try:
                launch_player_impact_background(
                    game_id=game_id,
                    season=season,
                    force=True,
                )

                st.rerun()

            except Exception as error:
                st.error(
                    "Could not restart Player Impact analysis."
                )

                st.code(
                    str(error)
                )

        return


# ============================================================
# Box score
# ============================================================

BOX_SCORE_RUNTIME_DIR = (
    ROOT_DIR
    / "results"
    / ".runtime"
    / "box_score"
)


def box_score_background_status(
    game_id,
):
    game_id = str(
        game_id
    )

    cache_path = (
        historical_box_score_cache_path(
            game_id
        )
    )

    if cache_path.exists():
        return {
            "state":
                "completed",
        }

    status_path = (
        BOX_SCORE_RUNTIME_DIR
        / f"{game_id}.json"
    )

    if not status_path.exists():
        return {
            "state":
                "missing",
        }

    try:
        return json.loads(
            status_path.read_text()
        )

    except Exception:
        return {
            "state":
                "missing",
        }


def launch_box_score_background(
    game_id,
    season,
):
    game_id = str(
        game_id
    )

    status = (
        box_score_background_status(
            game_id
        )
    )

    if status.get(
        "state"
    ) in {
        "running",
        "completed",
    }:
        return status

    BOX_SCORE_RUNTIME_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    status_path = (
        BOX_SCORE_RUNTIME_DIR
        / f"{game_id}.json"
    )

    status_path.write_text(
        json.dumps(
            {
                "state":
                    "running",

                "game_id":
                    game_id,

                "season":
                    season,
            }
        )
    )

    log_path = (
        BOX_SCORE_RUNTIME_DIR
        / f"{game_id}.log"
    )

    log_file = open(
        log_path,
        "a",
    )

    try:
        process = subprocess.Popen(
            [
                sys.executable,
                str(
                    ROOT_DIR
                    / "src"
                    / "run_box_score_worker.py"
                ),
                game_id,
                "--season",
                season,
            ],
            cwd=str(
                ROOT_DIR
            ),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    finally:
        log_file.close()

    return {
        "state":
            "running",

        "pid":
            process.pid,
    }


BOX_SCORE_CACHE_VERSION = "v1"


def historical_box_score_cache_path(
    game_id,
):
    return (
        ROOT_DIR
        / "data"
        / "cache"
        / "box_score"
        / BOX_SCORE_CACHE_VERSION
        / f"{str(game_id)}.pkl"
    )


def load_persistent_box_score(
    game_id,
):
    cache_path = (
        historical_box_score_cache_path(
            game_id
        )
    )

    if not cache_path.exists():
        return None

    try:
        with cache_path.open(
            "rb"
        ) as handle:
            payload = pickle.load(
                handle
            )

    except Exception:
        return None

    if not isinstance(
        payload,
        dict,
    ):
        return None

    if (
        payload.get(
            "cache_version"
        )
        != BOX_SCORE_CACHE_VERSION
    ):
        return None

    return payload.get(
        "box_score"
    )


def save_persistent_box_score(
    game_id,
    box_score,
):
    """
    Persist a completed historical box score.

    We only persist when advanced stats were successfully
    retrieved. If the advanced endpoint temporarily fails,
    Courtvision still renders traditional stats but retries
    on a future cold load instead of permanently caching the
    degraded response.
    """

    if not box_score.get(
        "advanced_available",
        False,
    ):
        return

    cache_path = (
        historical_box_score_cache_path(
            game_id
        )
    )

    cache_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path = (
        cache_path.with_suffix(
            ".pkl.tmp"
        )
    )

    payload = {
        "cache_version":
            BOX_SCORE_CACHE_VERSION,

        "game_id":
            str(game_id),

        "box_score":
            box_score,
    }

    try:
        with temp_path.open(
            "wb"
        ) as handle:
            pickle.dump(
                payload,
                handle,
                protocol=pickle.HIGHEST_PROTOCOL,
            )

        temp_path.replace(
            cache_path
        )

    except Exception:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass

        # Caching is an optimization only.
        return


def cached_historical_box_score(
    game_id,
):
    """
    Historical render path is disk-only.

    Network fetching happens in the detached box-score worker.
    """

    return (
        load_persistent_box_score(
            str(game_id)
        )
    )


@st.cache_data(
    ttl=30,
    show_spinner=False,
)
def cached_live_box_score(
    game_id,
):
    return fetch_box_score(
        game_id
    )


def format_box_stat(
    value,
):
    if value is None:
        return "—"

    try:
        if value != value:
            return "—"

        return str(
            int(
                round(
                    float(value)
                )
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        return "—"


def format_plus_minus(
    value,
):
    if value is None:
        return "—"

    try:
        if value != value:
            return "—"

        number = int(
            round(
                float(value)
            )
        )

        return f"{number:+d}"

    except (
        TypeError,
        ValueError,
    ):
        return "—"


def format_shooting_line(
    made,
    attempted,
):
    try:
        if (
            made is None
            or attempted is None
            or made != made
            or attempted != attempted
        ):
            return "—"

        return (
            f"{int(made)}-"
            f"{int(attempted)}"
        )

    except (
        TypeError,
        ValueError,
    ):
        return "—"


def format_advanced_number(
    value,
):
    try:
        if (
            value is None
            or value != value
        ):
            return "—"

        return (
            f"{float(value):.1f}"
        )

    except (
        TypeError,
        ValueError,
    ):
        return "—"


def format_advanced_percent(
    value,
):
    try:
        if (
            value is None
            or value != value
        ):
            return "—"

        return (
            f"{float(value) * 100:.1f}%"
        )

    except (
        TypeError,
        ValueError,
    ):
        return "—"


def normalize_box_position(
    value,
):
    if value is None:
        return "—"

    try:
        if value != value:
            return "—"
    except Exception:
        pass

    position = str(
        value
    ).strip()

    if not position:
        return "—"

    aliases = {
        "Guard": "G",
        "Forward": "F",
        "Center": "C",
        "Guard-Forward": "G-F",
        "Forward-Guard": "F-G",
        "Forward-Center": "F-C",
        "Center-Forward": "C-F",
    }

    return aliases.get(
        position,
        position,
    )


@st.cache_data(
    ttl=86400,
    show_spinner=False,
)
def cached_team_position_map(
    team_id,
    season,
):
    """
    Disk-only position lookup.

    Rendering must never block on CommonTeamRoster.
    Position caches are warmed by the detached historical
    box-score worker.
    """

    cache_path = (
        ROOT_DIR
        / "data"
        / "cache"
        / "positions"
        / "v1"
        / f"{season}_{int(team_id)}.pkl"
    )

    if not cache_path.exists():
        return {}

    try:
        with cache_path.open(
            "rb"
        ) as handle:
            payload = pickle.load(
                handle
            )

        if not isinstance(
            payload,
            dict,
        ):
            return {}

        return (
            payload.get(
                "positions",
                {},
            )
            or {}
        )

    except Exception:
        return {}


@st.cache_data(
    ttl=86400,
    show_spinner=False,
)
def cached_player_position(
    person_id,
):
    """
    Last-resort position lookup for players missing from
    the season roster response.
    """

    try:
        endpoint = (
            commonplayerinfo
            .CommonPlayerInfo(
                player_id=int(
                    person_id
                ),
                timeout=60,
            )
        )

        frames = (
            endpoint.get_data_frames()
        )

        if not frames:
            return "—"

        player_df = (
            frames[0]
            .copy()
        )

        if player_df.empty:
            return "—"

        row = (
            player_df.iloc[
                0
            ]
        )

        # nba_api versions have used both upper- and
        # title-style column naming in endpoint wrappers,
        # so support either defensively.
        position = None

        for column in [
            "POSITION",
            "Position",
            "position",
        ]:
            if column in player_df.columns:
                position = (
                    row.get(
                        column
                    )
                )

                break

        return (
            normalize_box_position(
                position
            )
        )

    except Exception:
        return "—"


def identify_box_score_starters(
    team_df,
):
    """
    Identify the starting five.

    Priority:
      1. explicit starter field, when available
      2. historical V3 position field
      3. first five rows as a fallback
    """

    starters = pd.Series(
        False,
        index=team_df.index,
        dtype=bool,
    )

    if "starter" in team_df.columns:
        values = (
            team_df[
                "starter"
            ]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.lower()
        )

        explicit = (
            values.isin(
                [
                    "true",
                    "1",
                    "yes",
                    "y",
                ]
            )
        )

        if explicit.sum() == 5:
            return explicit

    if "position" in team_df.columns:
        positioned = (
            team_df[
                "position"
            ]
            .fillna("")
            .astype(str)
            .str.strip()
            .ne("")
        )

        # Traditional V3 normally populates this for
        # the five starters.
        if positioned.sum() == 5:
            return positioned

    starters.iloc[
        :min(
            5,
            len(team_df),
        )
    ] = True

    return starters


def prepare_box_score_rows(
    team_df,
    season,
):
    """
    Build the traditional table.

    Important:
    numeric statistics remain numeric rather than being
    converted to strings. This fixes Streamlit sorting.
    """

    working = (
        team_df.copy()
        .reset_index(
            drop=True
        )
    )

    working[
        "_apiOrder"
    ] = range(
        len(working)
    )

    working[
        "_starter"
    ] = (
        identify_box_score_starters(
            working
        )
        .to_numpy()
    )

    # Default ordering:
    # five starters first, then bench.
    working = (
        working
        .sort_values(
            [
                "_starter",
                "_apiOrder",
            ],
            ascending=[
                False,
                True,
            ],
            kind="mergesort",
        )
        .reset_index(
            drop=True
        )
    )

    position_map = {}

    if (
        not working.empty
        and "teamId"
        in working.columns
    ):
        ids = (
            working[
                "teamId"
            ]
            .dropna()
        )

        if not ids.empty:
            position_map = (
                cached_team_position_map(
                    int(
                        ids.iloc[0]
                    ),
                    season,
                )
            )

    rows = []

    for _, row in (
        working.iterrows()
    ):
        minutes = str(
            row.get(
                "minutesDisplay",
                "",
            )
            or ""
        ).strip()

        comment = str(
            row.get(
                "comment",
                "",
            )
            or ""
        ).strip()

        played = bool(
            minutes
        )

        person_id = (
            row.get(
                "personId"
            )
        )

        roster_position = None

        try:
            if (
                person_id is not None
                and person_id == person_id
            ):
                roster_position = (
                    position_map.get(
                        int(person_id)
                    )
                )
        except (
            TypeError,
            ValueError,
        ):
            pass

        direct_position = (
            normalize_box_position(
                row.get(
                    "position",
                    "",
                )
            )
        )

        position = (
            roster_position
            if (
                roster_position
                and roster_position != "—"
            )
            else direct_position
        )

        # Do not perform per-player NBA API calls while
        # rendering. If neither the box score nor the cached
        # team roster provides a position, display an em dash.
        # The background box-score worker warms roster data.

        def numeric_stat(
            column,
        ):
            if not played:
                return pd.NA

            value = pd.to_numeric(
                pd.Series(
                    [
                        row.get(
                            column
                        )
                    ]
                ),
                errors="coerce",
            ).iloc[0]

            if pd.isna(value):
                return pd.NA

            return int(
                round(
                    float(value)
                )
            )

        rows.append(
            {
                "Player":
                    row.get(
                        "fullName",
                        "",
                    ),

                "POS":
                    position,

                "MIN":
                    (
                        minutes
                        if played
                        else (
                            comment
                            if comment
                            else "DNP"
                        )
                    ),

                "PTS":
                    numeric_stat(
                        "points"
                    ),

                "REB":
                    numeric_stat(
                        "reboundsTotal"
                    ),

                "AST":
                    numeric_stat(
                        "assists"
                    ),

                "STL":
                    numeric_stat(
                        "steals"
                    ),

                "BLK":
                    numeric_stat(
                        "blocks"
                    ),

                "TO":
                    numeric_stat(
                        "turnovers"
                    ),

                "FG":
                    (
                        format_shooting_line(
                            row.get(
                                "fieldGoalsMade"
                            ),
                            row.get(
                                "fieldGoalsAttempted"
                            ),
                        )
                        if played
                        else "—"
                    ),

                "3PT":
                    (
                        format_shooting_line(
                            row.get(
                                "threePointersMade"
                            ),
                            row.get(
                                "threePointersAttempted"
                            ),
                        )
                        if played
                        else "—"
                    ),

                "FT":
                    (
                        format_shooting_line(
                            row.get(
                                "freeThrowsMade"
                            ),
                            row.get(
                                "freeThrowsAttempted"
                            ),
                        )
                        if played
                        else "—"
                    ),

                "+/-":
                    numeric_stat(
                        "plusMinusPoints"
                    ),

                "_starter":
                    bool(
                        row[
                            "_starter"
                        ]
                    ),
            }
        )

    result = pd.DataFrame(
        rows
    )

    # Force nullable numeric dtype so Streamlit knows that
    # these are numbers instead of text.
    for column in [
        "PTS",
        "REB",
        "AST",
        "STL",
        "BLK",
        "TO",
        "+/-",
    ]:
        if column in result.columns:
            result[
                column
            ] = (
                pd.to_numeric(
                    result[
                        column
                    ],
                    errors="coerce",
                )
                .astype(
                    "Int64"
                )
            )

    return result



def prepare_advanced_box_score_rows(
    team_df,
):
    rows = []

    for _, row in (
        team_df.iterrows()
    ):
        minutes = str(
            row.get(
                "minutesDisplay",
                "",
            )
            or ""
        ).strip()

        if not minutes:
            continue

        rows.append(
            {
                "Player":
                    row.get(
                        "fullName",
                        "",
                    ),

                "ORtg":
                    format_advanced_number(
                        row.get(
                            "offensiveRating"
                        )
                    ),

                "DRtg":
                    format_advanced_number(
                        row.get(
                            "defensiveRating"
                        )
                    ),

                "Net":
                    format_advanced_number(
                        row.get(
                            "netRating"
                        )
                    ),

                "TS%":
                    format_advanced_percent(
                        row.get(
                            "trueShootingPercentage"
                        )
                    ),

                "eFG%":
                    format_advanced_percent(
                        row.get(
                            "effectiveFieldGoalPercentage"
                        )
                    ),

                "USG%":
                    format_advanced_percent(
                        row.get(
                            "usagePercentage"
                        )
                    ),

                "AST%":
                    format_advanced_percent(
                        row.get(
                            "assistPercentage"
                        )
                    ),

                "REB%":
                    format_advanced_percent(
                        row.get(
                            "reboundPercentage"
                        )
                    ),

                "Pace":
                    format_advanced_number(
                        row.get(
                            "pace"
                        )
                    ),

                "Poss":
                    format_advanced_number(
                        row.get(
                            "possessions"
                        )
                    ),

                "PIE":
                    format_advanced_percent(
                        row.get(
                            "PIE"
                        )
                    ),
            }
        )

    return rows


def render_box_team_header(
    team,
):
    tricode = (
        team[
            "tricode"
        ]
    )

    name = (
        team.get(
            "name",
            tricode,
        )
    )

    color = (
        team.get(
            "chart_color",
            "#9CA3AF",
        )
    )

    html = (
        f'<div style="'
        f'border-left:5px solid {color};'
        f'background:rgba(128,128,128,0.055);'
        f'border-radius:8px;'
        f'padding:0.70rem 0.95rem;'
        f'margin:0.25rem 0 0.65rem 0;'
        f'">'

        f'<div style="'
        f'display:flex;'
        f'align-items:baseline;'
        f'gap:0.65rem;'
        f'">'

        f'<span style="'
        f'font-size:1.45rem;'
        f'font-weight:800;'
        f'">'
        f'{tricode}'
        f'</span>'

        f'<span style="'
        f'color:{color};'
        f'font-size:0.92rem;'
        f'font-weight:650;'
        f'">'
        f'{name}'
        f'</span>'

        f'</div>'
        f'</div>'
    )

    st.markdown(
        html,
        unsafe_allow_html=True,
    )


def render_team_box_score(
    box_score,
    team,
    season,
    game_id,
):
    team_df = (
        get_team_players(
            box_score,
            team[
                "tricode"
            ],
        )
    )

    render_box_team_header(
        team
    )

    if team_df.empty:
        st.caption(
            "No box-score data available."
        )
        return

    prepared_df = (
        prepare_box_score_rows(
            team_df,
            season,
        )
    )

    # --------------------------------------------------------
    # Player filtering
    # --------------------------------------------------------

    view = st.segmented_control(
        "Players",
        options=[
            "All",
            "Starters",
            "Bench",
        ],
        default="All",
        key=(
            f"box_score_view_"
            f"{game_id}_"
            f"{team['tricode']}"
        ),
        label_visibility="collapsed",
    )

    if view == "Starters":
        table_df = (
            prepared_df[
                prepared_df[
                    "_starter"
                ]
            ]
            .copy()
        )

    elif view == "Bench":
        table_df = (
            prepared_df[
                ~prepared_df[
                    "_starter"
                ]
            ]
            .copy()
        )

    else:
        table_df = (
            prepared_df.copy()
        )

    table_df = (
        table_df
        .drop(
            columns=[
                "_starter",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    st.dataframe(
        table_df,
        width="stretch",
        hide_index=True,
        height=min(
            560,
            42
            + (
                max(
                    1,
                    len(table_df),
                )
                * 35
            ),
        ),
        column_config={
            "Player":
                st.column_config.TextColumn(
                    "Player",
                    width="large",
                ),

            "POS":
                st.column_config.TextColumn(
                    "POS",
                    width="small",
                ),

            "MIN":
                st.column_config.TextColumn(
                    "MIN",
                    width="small",
                ),

            "PTS":
                st.column_config.NumberColumn(
                    "PTS",
                    format="%d",
                ),

            "REB":
                st.column_config.NumberColumn(
                    "REB",
                    format="%d",
                ),

            "AST":
                st.column_config.NumberColumn(
                    "AST",
                    format="%d",
                ),

            "STL":
                st.column_config.NumberColumn(
                    "STL",
                    format="%d",
                ),

            "BLK":
                st.column_config.NumberColumn(
                    "BLK",
                    format="%d",
                ),

            "TO":
                st.column_config.NumberColumn(
                    "TO",
                    format="%d",
                ),

            "+/-":
                st.column_config.NumberColumn(
                    "+/-",
                    format="%+d",
                ),
        },
    )

    # --------------------------------------------------------
    # Preserve existing advanced-stat behavior
    # --------------------------------------------------------

    advanced_columns = [
        "offensiveRating",
        "defensiveRating",
        "netRating",
        "trueShootingPercentage",
        "effectiveFieldGoalPercentage",
        "usagePercentage",
    ]

    has_advanced = (
        all(
            column in team_df.columns
            for column
            in advanced_columns
        )
        and team_df[
            advanced_columns
        ]
        .notna()
        .any()
        .any()
    )

    if has_advanced:
        with st.expander(
            f"{team['tricode']} advanced stats"
        ):
            st.dataframe(
                prepare_advanced_box_score_rows(
                    team_df
                ),
                width="stretch",
                hide_index=True,
            )




def render_game_story(
    game_df,
    game_id,
    season,
    home_team_metadata,
    away_team_metadata,
    live=False,
):
    st.subheader(
        "Game Story"
    )

    st.caption(
        "Courtvision's whole-game read, combining game flow, "
        "momentum, win probability, and player impact."
    )

    home_team = (
        home_team_metadata[
            "tricode"
        ]
    )

    away_team = (
        away_team_metadata[
            "tricode"
        ]
    )

    player_summary = None

    if not live:
        player_summary = (
            cached_existing_player_summary(
                str(game_id)
            )
        )

    explanations = (
        cached_contextual_intelligence(
            game_df,
            home_team,
            away_team,
            player_summary,
        )
    )

    story = (
        build_game_story(
            game_df=game_df,
            explanations=explanations,
            home_team=home_team,
            away_team=away_team,
            player_summary=player_summary,
        )
    )

    if story is None:
        st.caption(
            "Game Story is unavailable for this game."
        )
        return

    metadata_by_team = {
        home_team:
            home_team_metadata,

        away_team:
            away_team_metadata,
    }

    winner = (
        story.get(
            "winner"
        )
    )

    winner_metadata = (
        metadata_by_team.get(
            winner,
            {},
        )
    )

    color = (
        winner_metadata.get(
            "chart_color",
            "#9CA3AF",
        )
    )

    lead = (
        story.get(
            "lead",
            "",
        )
    )

    subtitle = (
        story.get(
            "subtitle",
            "",
        )
    )

    header_html = (
        f'<div style="'
        f'border-left:5px solid {color};'
        f'background:rgba(128,128,128,0.055);'
        f'border-radius:10px;'
        f'padding:1.05rem 1.2rem;'
        f'margin-bottom:0.9rem;'
        f'">'

        f'<div style="'
        f'font-size:1.08rem;'
        f'font-weight:800;'
        f'line-height:1.35;'
        f'">'
        f'{lead}'
        f'</div>'

        f'<div style="'
        f'margin-top:0.3rem;'
        f'color:rgba(230,230,230,0.72);'
        f'font-size:0.93rem;'
        f'">'
        f'{subtitle}'
        f'</div>'

        f'</div>'
    )

    st.markdown(
        header_html,
        unsafe_allow_html=True,
    )

    metrics = (
        story.get(
            "metrics",
            [],
        )
    )

    if metrics:
        columns = (
            st.columns(
                len(metrics)
            )
        )

        for column, metric in zip(
            columns,
            metrics,
        ):
            with column:
                metric_html = (
                    f'<div style="'
                    f'background:rgba(128,128,128,0.035);'
                    f'border:1px solid rgba(160,160,160,0.16);'
                    f'border-radius:8px;'
                    f'padding:0.75rem 0.9rem;'
                    f'min-height:76px;'
                    f'">'

                    f'<div style="'
                    f'color:rgba(220,220,220,0.58);'
                    f'font-size:0.73rem;'
                    f'font-weight:700;'
                    f'text-transform:uppercase;'
                    f'letter-spacing:0.05em;'
                    f'">'
                    f'{metric["label"]}'
                    f'</div>'

                    f'<div style="'
                    f'margin-top:0.25rem;'
                    f'font-size:1.02rem;'
                    f'font-weight:800;'
                    f'color:{color};'
                    f'">'
                    f'{metric["value"]}'
                    f'</div>'

                    f'</div>'
                )

                st.markdown(
                    metric_html,
                    unsafe_allow_html=True,
                )

    sections = (
        story.get(
            "sections",
            [],
        )
    )

    # Keep Game Story concise and non-redundant.
    # Detailed momentum windows are already presented
    # in "Why the Game Changed".
    sections = [
        section
        for section in sections
        if str(
            section.get(
                "label",
                "",
            )
        ).strip().upper()
        in {
            "GAME FLOW",
            "KEY CONTRIBUTORS",
        }
    ]

    if sections:
        story_html = (
            '<div style="'
            'background:rgba(128,128,128,0.035);'
            'border:1px solid rgba(160,160,160,0.16);'
            'border-radius:10px;'
            'padding:0.35rem 1.15rem;'
            'margin-top:1rem;'
            '">'
        )

        for index, section in enumerate(
            sections
        ):
            if index > 0:
                story_html += (
                    '<div style="'
                    'border-top:1px solid '
                    'rgba(160,160,160,0.12);'
                    '"></div>'
                )

            story_html += (
                '<div style="'
                'padding:0.9rem 0;'
                '">'

                '<div style="'
                'font-size:0.75rem;'
                'font-weight:800;'
                'text-transform:uppercase;'
                'letter-spacing:0.055em;'
                f'color:{color};'
                'margin-bottom:0.32rem;'
                '">'
                f'{section["label"]}'
                '</div>'

                '<div style="'
                'font-size:0.97rem;'
                'line-height:1.55;'
                'color:rgba(240,240,240,0.90);'
                '">'
                f'{section["text"]}'
                '</div>'

                '</div>'
            )

        story_html += (
            '</div>'
        )

        st.markdown(
            story_html,
            unsafe_allow_html=True,
        )



def render_contextual_game_explanations(
    game_df,
    game_id,
    season,
    home_team_metadata,
    away_team_metadata,
    live=False,
):
    """
    Explain the most important multi-play swings using
    deterministic Courtvision signals.

    This is intentionally not an LLM-generated recap.
    Every statement is derived from the game timeline,
    momentum detector, and validated player WPA layer.
    """

    st.subheader(
        "Why the Game Changed"
    )

    st.caption(
        "Courtvision highlights the most distinct "
        "game-changing stretches, prioritizing meaningful "
        "score-state and win-probability shifts."
    )

    home_team = (
        home_team_metadata[
            "tricode"
        ]
    )

    away_team = (
        away_team_metadata[
            "tricode"
        ]
    )

    player_summary = None

    # Historical player WPA is validated. Live player WPA
    # remains intentionally disabled.
    if not live:
        try:
            impact = (
                cached_player_impact(
                    str(game_id),
                    season,
                    "v3",
                )
            )

            player_summary = (
                impact.get(
                    "player_summary"
                )
            )

        except Exception:
            player_summary = None

    explanations = (
        cached_contextual_intelligence(
            game_df,
            home_team,
            away_team,
            player_summary,
        )
    )

    if not explanations:
        st.caption(
            "No contextual swing explanations cleared "
            "the current momentum thresholds."
        )

        return

    # Display the selected explanation windows in
    # actual game chronology.
    #
    # This does NOT change which explanations qualify or
    # their validated context scores. It only changes the
    # presentation order.
    def explanation_chronology_key(
        explanation,
    ):
        period = int(
            explanation.get(
                "startPeriod",
                999,
            )
        )

        clock = str(
            explanation.get(
                "startClock",
                "",
            )
        )

        remaining_seconds = -1.0

        try:
            if (
                clock.startswith(
                    "PT"
                )
                and clock.endswith(
                    "S"
                )
            ):
                clock_body = (
                    clock[
                        2:-1
                    ]
                )

                if "M" in clock_body:
                    minutes_text, seconds_text = (
                        clock_body.split(
                            "M",
                            1,
                        )
                    )

                    remaining_seconds = (
                        60.0
                        * float(
                            minutes_text
                            or 0
                        )
                        + float(
                            seconds_text
                            or 0
                        )
                    )

                else:
                    remaining_seconds = float(
                        clock_body
                        or 0
                    )

        except (
            TypeError,
            ValueError,
        ):
            remaining_seconds = -1.0

        # Earlier periods come first.
        #
        # Inside an NBA period, a larger remaining clock
        # occurs earlier, so negate remaining_seconds.
        return (
            period,
            -remaining_seconds,
        )

    explanations = sorted(
        explanations,
        key=(
            explanation_chronology_key
        ),
    )

    # --------------------------------------------------------
    # Display-only narrative diversity
    # --------------------------------------------------------
    #
    # Contextual Intelligence may identify several valid
    # momentum windows that tell essentially the same story
    # (for example, three separate comeback runs by one team).
    #
    # Keep the underlying validated explanations untouched,
    # but avoid repeating the same narrative on the page.
    #
    # For repeated team + narrative combinations, prefer the
    # moment with the strongest game-state consequence:
    # tie / lead change > separation > raw WP swing.
    # --------------------------------------------------------

    def explanation_narrative_type(
        explanation,
    ):
        headline = str(
            explanation.get(
                "headline",
                "",
            )
        ).lower()

        if "broke the tie" in headline:
            return "broke_tie"

        if "flipped the game" in headline:
            return "flipped_game"

        if "pulled away" in headline:
            return "pulled_away"

        if "surged back" in headline:
            return "surged_back"

        return headline

    def explanation_display_score(
        explanation,
    ):
        headline = str(
            explanation.get(
                "headline",
                "",
            )
        ).lower()

        summary = str(
            explanation.get(
                "summary",
                "",
            )
        ).lower()

        score = float(
            explanation.get(
                "winProbabilitySwingPoints",
                0.0,
            )
        )

        # Most meaningful state changes.
        if (
            "tie the game" in summary
            or "tied the game" in summary
            or "broke the tie" in headline
        ):
            score += 100.0

        if (
            "turning a" in summary
            and "deficit into a" in summary
            and "lead" in summary
        ):
            score += 90.0

        if "flipped the game" in headline:
            score += 80.0

        if "pulled away" in headline:
            score += 60.0

        if (
            "extending the lead" in summary
            or "building a" in summary
            and "lead" in summary
        ):
            score += 40.0

        return score

    best_by_narrative = {}

    for explanation in explanations:
        key = (
            str(
                explanation.get(
                    "team",
                    "",
                )
            ),
            explanation_narrative_type(
                explanation
            ),
        )

        current = (
            best_by_narrative.get(
                key
            )
        )

        if (
            current is None
            or explanation_display_score(
                explanation
            )
            > explanation_display_score(
                current
            )
        ):
            best_by_narrative[
                key
            ] = explanation

    explanations = list(
        best_by_narrative.values()
    )

    # Rank the remaining distinct narratives by how much
    # they changed the actual game state.
    ranked_explanations = sorted(
        explanations,
        key=(
            explanation_display_score
        ),
        reverse=True,
    )

    # Keep the section narratively balanced:
    #
    # - at most four explanations overall;
    # - at most two explanations for either team;
    # - allow fewer than four when additional cards would
    #   mostly repeat the same team's story.
    diverse_explanations = []
    team_counts = {}

    for explanation in ranked_explanations:
        team = str(
            explanation.get(
                "team",
                "",
            )
        )

        current_count = (
            team_counts.get(
                team,
                0,
            )
        )

        if current_count >= 2:
            continue

        diverse_explanations.append(
            explanation
        )

        team_counts[
            team
        ] = (
            current_count + 1
        )

        if len(
            diverse_explanations
        ) >= 4:
            break

    explanations = diverse_explanations

    # Always present the final selected narratives in
    # actual game chronology rather than importance order.
    explanations = sorted(
        explanations,
        key=(
            explanation_chronology_key
        ),
    )

    team_metadata = {
        home_team:
            home_team_metadata,

        away_team:
            away_team_metadata,
    }

    for index, explanation in enumerate(
        explanations,
        start=1,
    ):
        team = (
            explanation[
                "team"
            ]
        )

        metadata = (
            team_metadata.get(
                team,
                {},
            )
        )

        color = (
            metadata.get(
                "chart_color",
                "#9CA3AF",
            )
        )

        swing = (
            explanation[
                "winProbabilitySwingPoints"
            ]
        )

        html = (
            f'<div style="'
            f'border-left:4px solid {color};'
            f'background:rgba(128,128,128,0.055);'
            f'border-radius:9px;'
            f'padding:0.95rem 1.05rem;'
            f'margin-bottom:0.75rem;'
            f'">'

            f'<div style="'
            f'display:flex;'
            f'justify-content:space-between;'
            f'align-items:baseline;'
            f'gap:1rem;'
            f'">'

            f'<span style="'
            f'font-size:1.02rem;'
            f'font-weight:800;'
            f'">'
            f'{index}. '
            f'{explanation["headline"]}'
            f'</span>'

            f'<span style="'
            f'color:{color};'
            f'font-weight:800;'
            f'white-space:nowrap;'
            f'">'
            f'+{swing:.1f} pp'
            f'</span>'

            f'</div>'

            f'<div style="'
            f'margin-top:0.45rem;'
            f'line-height:1.5;'
            f'color:rgba(235,235,235,0.90);'
            f'">'
            f'{explanation["summary"]}'
            f'</div>'

            f'</div>'
        )

        st.markdown(
            html,
            unsafe_allow_html=True,
        )

        details = (
            explanation.get(
                "details",
                [],
            )
        )

        if details:
            with st.expander(
                "Supporting context",
                expanded=False,
            ):
                for detail in details:
                    st.markdown(
                        f"- {detail}"
                    )




@st.fragment(
    run_every=2,
)
def poll_historical_box_score(
    game_id,
):
    """
    Poll only for completion of the detached historical
    box-score worker.

    Network work is never performed in this fragment.
    """

    game_id = str(
        game_id
    )

    cache_path = (
        historical_box_score_cache_path(
            game_id
        )
    )

    if cache_path.exists():
        st.rerun()
        return


def render_box_score(
    game_id,
    season,
    away_team,
    home_team,
    live=False,
):
    st.subheader(
        "Box Score"
    )

    st.caption(
        "Starting five are listed first, followed by the "
        "bench. Use the player filter or click any numeric "
        "column header to sort."
    )

    try:
        if live:
            box_score = (
                cached_live_box_score(
                    str(game_id)
                )
            )

        else:
            box_score = (
                cached_historical_box_score(
                    str(game_id)
                )
            )

            if box_score is None:
                status = (
                    box_score_background_status(
                        str(game_id)
                    )
                )

                if (
                    status.get(
                        "state"
                    )
                    == "missing"
                ):
                    status = (
                        launch_box_score_background(
                            game_id=str(
                                game_id
                            ),
                            season=season,
                        )
                    )

                if (
                    status.get(
                        "state"
                    )
                    in {
                        "running",
                        "missing",
                    }
                ):
                    st.info(
                        "Loading the box score in the "
                        "background. The rest of Courtvision "
                        "is available while it finishes."
                    )

                    poll_historical_box_score(
                        str(game_id)
                    )

                    return

                if (
                    status.get(
                        "state"
                    )
                    == "failed"
                ):
                    st.info(
                        "Box score is not currently available."
                    )

                    error = (
                        status.get(
                            "error"
                        )
                    )

                    if error:
                        with st.expander(
                            "Box score details"
                        ):
                            st.code(
                                str(error)
                            )

                    return

                # The worker may have completed between the
                # initial check and this point.
                box_score = (
                    load_persistent_box_score(
                        str(game_id)
                    )
                )

                if box_score is None:
                    st.info(
                        "Loading the box score in the "
                        "background."
                    )
                    return

    except Exception as error:
        st.info(
            "Box score is not available "
            "for this game."
        )

        with st.expander(
            "Box score details"
        ):
            st.code(
                str(error)
            )

        return

    render_team_box_score(
        box_score,
        away_team,
        season,
        str(game_id),
    )

    st.markdown(
        "<div style='height:1rem'></div>",
        unsafe_allow_html=True,
    )

    render_team_box_score(
        box_score,
        home_team,
        season,
        str(game_id),
    )

    if not box_score.get(
        "advanced_available",
        False,
    ):
        st.caption(
            "Advanced statistics are "
            "currently unavailable."
        )


# ============================================================
# Momentum runs
# ============================================================

def format_momentum_duration(
    seconds,
):
    seconds = max(
        0,
        int(
            round(
                float(
                    seconds
                )
            )
        ),
    )

    minutes = (
        seconds // 60
    )

    remaining = (
        seconds % 60
    )

    return (
        f"{minutes}:{remaining:02d}"
    )


def format_momentum_location(
    period,
    clock,
):
    return (
        f"{format_period_label(period)} "
        f"{normalize_clock_display(clock)}"
    )


def render_momentum_card(
    run,
    team_metadata,
):
    team = (
        run[
            "beneficiaryTeam"
        ]
    )

    opponent = (
        run[
            "opponentTeam"
        ]
    )

    color = (
        team_metadata.get(
            "chart_color",
            "#9CA3AF",
        )
    )

    swing = float(
        run[
            "winProbabilitySwingPoints"
        ]
    )

    before = (
        float(
            run[
                "winProbabilityBefore"
            ]
        )
        * 100.0
    )

    after = (
        float(
            run[
                "winProbabilityAfter"
            ]
        )
        * 100.0
    )

    start_location = (
        format_momentum_location(
            run[
                "startPeriod"
            ],
            run[
                "startClock"
            ],
        )
    )

    end_location = (
        format_momentum_location(
            run[
                "endPeriod"
            ],
            run[
                "endClock"
            ],
        )
    )

    duration = (
        format_momentum_duration(
            run[
                "durationSeconds"
            ]
        )
    )

    team_points = int(
        run[
            "beneficiaryPoints"
        ]
    )

    opponent_points = int(
        run[
            "opponentPoints"
        ]
    )

    transitions = int(
        run[
            "transitions"
        ]
    )

    # Construct HTML without leading indentation.
    # Indented HTML inside a Markdown string can be
    # interpreted by Streamlit as a code block.
    html_block = (
        f'<div style="'
        f'border-left:4px solid {color};'
        f'border-radius:8px;'
        f'padding:0.85rem 1rem;'
        f'margin-bottom:0.75rem;'
        f'background:rgba(128,128,128,0.06);'
        f'">'

        f'<div style="'
        f'display:flex;'
        f'justify-content:space-between;'
        f'align-items:baseline;'
        f'gap:1rem;'
        f'">'

        f'<span style="'
        f'font-weight:750;'
        f'font-size:1.02rem;'
        f'">'
        f'{team} momentum run'
        f'</span>'

        f'<span style="'
        f'color:{color};'
        f'font-weight:800;'
        f'font-variant-numeric:tabular-nums;'
        f'white-space:nowrap;'
        f'">'
        f'+{swing:.1f} pp'
        f'</span>'

        f'</div>'

        f'<div style="'
        f'margin-top:0.35rem;'
        f'color:rgba(230,230,230,0.82);'
        f'">'
        f'{start_location} → {end_location}'
        f' · {duration}'
        f'</div>'

        f'<div style="'
        f'margin-top:0.45rem;'
        f'font-weight:600;'
        f'">'
        f'{team} win probability: '
        f'{before:.1f}% → {after:.1f}%'
        f'</div>'

        f'<div style="'
        f'margin-top:0.25rem;'
        f'color:rgba(230,230,230,0.78);'
        f'">'
        f'Scoring stretch: '
        f'{team} {team_points}–{opponent_points} {opponent}'
        f' · {transitions} state transitions'
        f'</div>'

        f'</div>'
    )

    st.markdown(
        html_block,
        unsafe_allow_html=True,
    )




@st.cache_data(
    ttl=86400,
    show_spinner=False,
)
def cached_momentum_intelligence(
    game_df,
    home_team,
    away_team,
):
    return (
        detect_momentum_runs(
            game_df,
            home_team=home_team,
            away_team=away_team,
            top_k=3,
        )
    )


@st.cache_data(
    ttl=86400,
    show_spinner=False,
)
def cached_contextual_intelligence(
    game_df,
    home_team,
    away_team,
    player_summary,
):
    momentum = (
        cached_momentum_intelligence(
            game_df,
            home_team,
            away_team,
        )
    )

    return (
        build_contextual_explanations(
            game_df=game_df,
            momentum_result=momentum,
            home_team=home_team,
            away_team=away_team,
            player_summary=player_summary,
            top_k=4,
        )
    )


def render_momentum_runs(
    game_df,
    home_team_metadata,
    away_team_metadata,
):
    st.subheader(
        "Momentum Runs"
    )

    st.caption(
        "Multi-play stretches where one team's modeled "
        "chance of winning rose substantially over a short "
        "sequence. These values show net observed win-"
        "probability movement across the stretch; they are "
        "not sums of player WPA."
    )

    result = (
        cached_momentum_intelligence(
            game_df,
            home_team_metadata[
                "tricode"
            ],
            away_team_metadata[
                "tricode"
            ],
        )
    )

    home_runs = (
        result[
            "home_runs"
        ]
    )

    away_runs = (
        result[
            "away_runs"
        ]
    )

    if (
        not home_runs
        and not away_runs
    ):
        st.caption(
            "No momentum runs cleared the current "
            "detection thresholds in this game."
        )

        return

    home_col, away_col = (
        st.columns(
            2
        )
    )

    with home_col:
        st.markdown(
            f"### "
            f"{home_team_metadata['tricode']}"
        )

        if home_runs:
            for run in home_runs:
                render_momentum_card(
                    run,
                    home_team_metadata,
                )

        else:
            st.caption(
                "No qualifying run."
            )

    with away_col:
        st.markdown(
            f"### "
            f"{away_team_metadata['tricode']}"
        )

        if away_runs:
            for run in away_runs:
                render_momentum_card(
                    run,
                    away_team_metadata,
                )

        else:
            st.caption(
                "No qualifying run."
            )




def render_game(

    result,

    game_id,

    season,

    live=False,

):

    game_df = (

        result[

            "timeline"

        ]

    )



    home_swings = (

        result[

            "home_swings"

        ]

    )



    away_swings = (

        result[

            "away_swings"

        ]

    )



    home_team = (

        get_team_metadata(

            result[

                "home_team_id"

            ]

        )

    )



    away_team = (

        get_team_metadata(

            result[

                "away_team_id"

            ]

        )

    )


    # Matchup-wide display palette
    #
    # Resolve visually distinct, team-authentic
    # colors once for the entire page. Every
    # downstream component then reads the same
    # local chart_color values.
    matchup_styles = (
        resolve_matchup_chart_styles(
            home_team,
            away_team,
        )
    )

    # Work with local copies so this matchup does
    # not modify the global TEAM_METADATA registry.
    home_team = dict(
        home_team
    )

    away_team = dict(
        away_team
    )

    home_team[
        "chart_color"
    ] = matchup_styles[
        "home_color"
    ]

    away_team[
        "chart_color"
    ] = matchup_styles[
        "away_color"
    ]

    if live:

        home_score = (

            result[

                "current_home_score"

            ]

        )



        away_score = (

            result[

                "current_away_score"

            ]

        )



        center_status = (

            result[

                "display_status"

            ]

        )



        st.markdown(

            '<div class="live-indicator">'

            '● LIVE MODE'

            '</div>',

            unsafe_allow_html=True,

        )



    else:

        home_score = (

            result[

                "final_home_score"

            ]

        )



        away_score = (

            result[

                "final_away_score"

            ]

        )



        center_status = (

            "FINAL"

        )





    home_record = (

        format_pregame_record(

            result[

                "home_pre_game_wins"

            ],

            result[

                "home_pre_game_losses"

            ],

        )

    )



    away_record = (

        format_pregame_record(

            result[

                "away_pre_game_wins"

            ],

            result[

                "away_pre_game_losses"

            ],

        )

    )





    away_col, center_col, home_col = (

        st.columns(

            [

                2,

                1,

                2,

            ]

        )

    )





    with away_col:

        render_team_logo(

            away_team

        )



        away_color = (

            away_team.get(

                "chart_color",

                "#9CA3AF",

            )

        )



        st.markdown(

            (

                "<div "

                "class='courtvision-team' "

                "style='border-top:3px solid "

                f"{away_color};'>"



                "<div "

                "class='courtvision-team-code'>"

                f"{away_team['tricode']}"

                "</div>"



                "<div "

                "class='courtvision-score'>"

                f"{away_score}"

                "</div>"



                "<div "

                "class='courtvision-team-name'>"

                f"{away_team['name']}"

                "</div>"



                "<div "

                "class='courtvision-record'>"

                f"Pregame: {away_record}"

                "</div>"



                "</div>"

            ),

            unsafe_allow_html=True,

        )





    with center_col:

        st.markdown(

            (

                "<div "

                "class='courtvision-status'>"

                f"{center_status}"

                "</div>"

            ),

            unsafe_allow_html=True,

        )





    with home_col:

        render_team_logo(

            home_team

        )



        home_color = (

            home_team.get(

                "chart_color",

                "#9CA3AF",

            )

        )



        st.markdown(

            (

                "<div "

                "class='courtvision-team' "

                "style='border-top:3px solid "

                f"{home_color};'>"



                "<div "

                "class='courtvision-team-code'>"

                f"{home_team['tricode']}"

                "</div>"



                "<div "

                "class='courtvision-score'>"

                f"{home_score}"

                "</div>"



                "<div "

                "class='courtvision-team-name'>"

                f"{home_team['name']}"

                "</div>"



                "<div "

                "class='courtvision-record'>"

                f"Pregame: {home_record}"

                "</div>"



                "</div>"

            ),

            unsafe_allow_html=True,

        )





    st.divider()



    st.subheader(
        "Game Summary"
    )

    current_home_wp = float(
        result[
            "current_home_win_probability"
        ]
    )

    current_away_wp = (
        1.0
        - current_home_wp
    )

    display_home_wp = (
        current_home_wp
    )

    display_away_wp = (
        current_away_wp
    )

    home_metric, away_metric, state_metric = (
        st.columns(
            3
        )
    )

    if live:
        home_label = (
            f"Current "
            f"{home_team['tricode']} "
            "Win Probability"
        )

        away_label = (
            f"Current "
            f"{away_team['tricode']} "
            "Win Probability"
        )

    else:
        home_label = (
            f"{home_team['tricode']} "
            "Pregame Win Expectation"
        )

        away_label = (
            f"{away_team['tricode']} "
            "Pregame Win Expectation"
        )

        try:
            _, rating_history = (
                cached_team_season_intelligence(
                    season
                )
            )

            normalized_game_id = (
                str(
                    game_id
                )
                .zfill(
                    10
                )
            )

            normalized_history_ids = (
                rating_history[
                    "gameId"
                ]
                .astype(
                    str
                )
                .str.zfill(
                    10
                )
            )

            rating_game_rows = (
                rating_history.loc[
                    normalized_history_ids
                    == normalized_game_id
                ]
            )

            home_rating_row = (
                rating_game_rows.loc[
                    rating_game_rows[
                        "team"
                    ]
                    == home_team[
                        "tricode"
                    ]
                ]
            )

            away_rating_row = (
                rating_game_rows.loc[
                    rating_game_rows[
                        "team"
                    ]
                    == away_team[
                        "tricode"
                    ]
                ]
            )

            if (
                len(
                    home_rating_row
                )
                == 1
                and len(
                    away_rating_row
                )
                == 1
            ):
                display_home_wp = float(
                    home_rating_row.iloc[
                        0
                    ][
                        "pregameWinProbability"
                    ]
                )

                display_away_wp = float(
                    away_rating_row.iloc[
                        0
                    ][
                        "pregameWinProbability"
                    ]
                )

            else:
                display_home_wp = None
                display_away_wp = None

        except Exception:
            display_home_wp = None
            display_away_wp = None

    with home_metric:
        st.metric(
            home_label,
            (
                f"{display_home_wp:.1%}"
                if display_home_wp
                is not None
                else "N/A"
            ),
        )

    with away_metric:
        st.metric(
            away_label,
            (
                f"{display_away_wp:.1%}"
                if display_away_wp
                is not None
                else "N/A"
            ),
        )

    with state_metric:
        if live:
            st.metric(
                "Game State",
                center_status,
            )

        else:
            winner = (
                home_team["tricode"]
                if home_score > away_score
                else away_team["tricode"]
            )

            loser = (
                away_team["tricode"]
                if winner
                == home_team["tricode"]
                else home_team["tricode"]
            )

            winner_score = (
                home_score
                if winner
                == home_team["tricode"]
                else away_score
            )

            loser_score = (
                away_score
                if winner
                == home_team["tricode"]
                else home_score
            )

            st.metric(
                "Final Result",
                (
                    f"{winner} "
                    f"{winner_score}–"
                    f"{loser_score} "
                    f"{loser}"
                ),
            )

    if live:
        st.caption(
            "Current Win Probability is Courtvision's "
            "model estimate for each team's chance of "
            "winning at the latest available game state."
        )

    else:
        st.caption(
            "Pregame Win Expectation is the frozen "
            "Team Courtvision Rating model's estimate "
            "of each team's chance of winning before tipoff."
        )


    figure = (

        build_win_probability_plot(

            game_df,

            home_swings,

            away_swings,

            home_team,

            away_team,

        )

    )
    st.caption(
        "Both lines show each team's modeled chance "
        "of winning. Turning-point values are always "
        "expressed from the benefiting team's perspective."
    )




    st.plotly_chart(

        figure,

        width="stretch",

        config={

            "displayModeBar":

                False,

        },

    )





    render_game_story(
        game_df=game_df,
        game_id=game_id,
        season=season,
        home_team_metadata=home_team,
        away_team_metadata=away_team,
        live=live,
    )

    st.divider()

    render_player_impact(

        game_id=game_id,

        season=season,

        home_team_metadata=home_team,

        away_team_metadata=away_team,

        live=live,

    )





    st.divider()

    render_contextual_game_explanations(
        game_df=game_df,
        game_id=game_id,
        season=season,
        home_team_metadata=home_team,
        away_team_metadata=away_team,
        live=live,
    )

    with st.expander(
        "View all detected momentum runs",
        expanded=False,
    ):
        render_momentum_runs(
            game_df,
            home_team,
            away_team,
        )

    st.divider()

    st.subheader(
        "Biggest Turning Points"
    )

    home_column, away_column = (
        st.columns(
            2
        )
    )

    with home_column:
        st.markdown(
            f"## {home_team['tricode']} Turning Points"
        )

        for _, row in home_swings.iterrows():
            render_swing_card(
                row,
                home_team,
                "home",
            )

    with away_column:
        st.markdown(
            f"## {away_team['tricode']} Turning Points"
        )

        for _, row in away_swings.iterrows():
            render_swing_card(
                row,
                away_team,
                "away",
            )

    if not live:
        st.divider()

        render_historical_team_rating(
            game_id=game_id,
            season=season,
            home_team_metadata=home_team,
            away_team_metadata=away_team,
        )

    st.divider()

    render_box_score(
        game_id=game_id,
        season=season,
        away_team=away_team,
        home_team=home_team,
        live=live,
    )

    st.divider()

    with st.expander(

        "View prediction timeline"

    ):

        st.dataframe(

            game_df,

            width="stretch",

        )





# ============================================================

# Historical

# ============================================================



HISTORICAL_ANALYSIS_CACHE_VERSION = "v1_v7"



def historical_analysis_cache_dir():
    return (
        ROOT_DIR
        / "data"
        / "cache"
        / "analysis"
        / HISTORICAL_ANALYSIS_CACHE_VERSION
    )


def historical_analysis_cache_path(
    game_id,
    season,
    top_k,
):
    safe_season = (
        str(season)
        .replace("/", "-")
        .replace(" ", "_")
    )

    return (
        historical_analysis_cache_dir()
        / (
            f"{safe_season}_"
            f"{str(game_id)}_"
            f"top{int(top_k)}.pkl"
        )
    )


def load_persistent_historical_analysis(
    game_id,
    season,
    top_k,
):
    cache_path = (
        historical_analysis_cache_path(
            game_id=game_id,
            season=season,
            top_k=top_k,
        )
    )

    if not cache_path.exists():
        return None

    try:
        with cache_path.open("rb") as handle:
            payload = pickle.load(
                handle
            )

    except Exception:
        # A stale/corrupt cache should never prevent
        # Courtvision from analyzing the game normally.
        return None

    if not isinstance(
        payload,
        dict,
    ):
        return None

    if (
        payload.get(
            "cache_version"
        )
        != HISTORICAL_ANALYSIS_CACHE_VERSION
    ):
        return None

    return payload.get(
        "result"
    )


def save_persistent_historical_analysis(
    game_id,
    season,
    top_k,
    result,
):
    cache_path = (
        historical_analysis_cache_path(
            game_id=game_id,
            season=season,
            top_k=top_k,
        )
    )

    cache_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path = (
        cache_path.with_suffix(
            ".pkl.tmp"
        )
    )

    payload = {
        "cache_version":
            HISTORICAL_ANALYSIS_CACHE_VERSION,

        "game_id":
            str(game_id),

        "season":
            str(season),

        "top_k":
            int(top_k),

        "result":
            result,
    }

    try:
        with temp_path.open(
            "wb"
        ) as handle:
            pickle.dump(
                payload,
                handle,
                protocol=pickle.HIGHEST_PROTOCOL,
            )

        temp_path.replace(
            cache_path
        )

    except Exception:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass

        # Cache writing is an optimization only.
        # Never fail the game analysis because of it.
        return


@st.cache_data(
    ttl=86400,
    show_spinner=False,
)
def cached_historical_analysis(
    game_id,
    season,
    game_date,
    top_k=3,
):
    """
    Historical analysis cache hierarchy:

      1. Streamlit in-memory cache
      2. persistent versioned disk cache
      3. analyze_live_game() fallback

    Completed games are immutable, so once Courtvision has
    analyzed a historical game there is no reason to rebuild
    the V7 timeline after every application restart.
    """

    game_id = str(
        game_id
    )

    cached_result = (
        load_persistent_historical_analysis(
            game_id=game_id,
            season=season,
            top_k=top_k,
        )
    )

    if cached_result is not None:
        return cached_result

    result = analyze_live_game(
        game_id=game_id,
        season=season,
        game_date=game_date,
        top_k=top_k,
        assume_final=True,
    )

    save_persistent_historical_analysis(
        game_id=game_id,
        season=season,
        top_k=top_k,
        result=result,
    )

    return result


def get_team_metadata_by_tricode(
    tricode,
):
    tricode = str(
        tricode
    ).upper()

    for metadata in (
        TEAM_METADATA.values()
    ):
        if (
            metadata.get(
                "tricode"
            )
            == tricode
        ):
            return metadata

    return {
        "name":
            tricode,

        "tricode":
            tricode,

        "primary_color":
            "#6B7280",

        "secondary_color":
            "#9CA3AF",

        "chart_color":
            "#58A6FF",

        "logo":
            None,
    }





def render_recent_form_team(
    tricode,
    delta,
):
    metadata = (
        get_team_metadata_by_tricode(
            tricode
        )
    )

    color = metadata.get(
        "chart_color",
        "#9CA3AF",
    )

    logo = metadata.get(
        "logo"
    )

    row = st.container(
        border=True,
    )

    with row:
        logo_col, name_col, delta_col = (
            st.columns(
                [
                    1,
                    4,
                    2,
                ],
                vertical_alignment="center",
            )
        )

        with logo_col:
            if (
                logo
                and Path(
                    logo
                ).exists()
            ):
                st.image(
                    logo,
                    width=34,
                )

        with name_col:
            st.markdown(
                (
                    f"<div style='"
                    f"border-left: 4px solid {color}; "
                    "padding-left: 10px;"
                    "'>"
                    f"<strong>{html.escape(str(tricode))}</strong>"
                    "<br>"
                    "<span style='opacity:0.65; "
                    "font-size:0.82rem;'>"
                    f"{html.escape(metadata.get('name', ''))}"
                    "</span>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )

        with delta_col:
            delta_color = (
                "#2ECC71"
                if float(
                    delta
                ) >= 0
                else "#FF5C77"
            )

            st.markdown(
                (
                    "<div style='"
                    "text-align:right; "
                    "font-size:1.15rem; "
                    "font-weight:700; "
                    f"color:{delta_color};"
                    "'>"
                    f"{float(delta):+.1f}"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )





def build_rating_change_explanation(
    row,
):
    team = str(
        row[
            "team"
        ]
    )

    opponent = str(
        row[
            "opponent"
        ]
    )

    team_win = int(
        row[
            "teamWin"
        ]
    )

    rating_before = float(
        row[
            "ratingBefore"
        ]
    )

    rating_after = float(
        row[
            "ratingAfter"
        ]
    )

    opponent_rating = float(
        row[
            "opponentRatingBefore"
        ]
    )

    expected = float(
        row[
            "pregameWinProbability"
        ]
    )

    rating_change = float(
        row[
            "ratingChange"
        ]
    )

    signed_margin = float(
        row[
            "signedMargin"
        ]
    )

    margin = abs(
        signed_margin
    )

    multiplier = float(
        row[
            "dominanceMultiplier"
        ]
    )

    rating_difference = (
        rating_before
        - opponent_rating
    )

    if rating_difference > 1e-9:
        opponent_context = (
            f"{team} entered rated "
            f"{abs(rating_difference):.1f} points "
            f"above {opponent}."
        )

    elif rating_difference < -1e-9:
        opponent_context = (
            f"{team} entered rated "
            f"{abs(rating_difference):.1f} points "
            f"below {opponent}."
        )

    else:
        opponent_context = (
            "The teams entered with equal ratings."
        )

    if team_win == 1:
        result_text = (
            f"{team} gained "
            f"{abs(rating_change):.1f} rating points "
            f"after beating {opponent} "
            f"by {margin:.0f}."
        )

    else:
        result_text = (
            f"{team} lost "
            f"{abs(rating_change):.1f} rating points "
            f"after losing to {opponent} "
            f"by {margin:.0f}."
        )

    expectation_text = (
        f"{team} had a "
        f"{expected * 100.0:.1f}% "
        "pregame win expectation. "
        f"{opponent_context}"
    )

    dominance_text = (
        f"The {margin:.0f}-point margin produced "
        f"a {multiplier:.3f}× "
        "Courtvision dominance multiplier."
    )

    league_rank = int(
        row[
            "leagueRankAfterGame"
        ]
    )

    movement_text = (
        f"The rating moved from "
        f"{rating_before:.1f} "
        f"to {rating_after:.1f}, "
        f"leaving {team} ranked "
        f"#{league_rank} in the league."
    )

    return (
        f"{result_text} "
        f"{expectation_text} "
        f"{dominance_text} "
        f"{movement_text}"
    )





def render_season_team_identity(
    metadata,
    subtitle=None,
    logo_width=72,
):
    logo = metadata.get(
        "logo"
    )

    color = metadata.get(
        "chart_color",
        "#58A6FF",
    )

    logo_col, text_col = (
        st.columns(
            [
                1,
                7,
            ],
            vertical_alignment="center",
        )
    )

    with logo_col:
        if (
            logo
            and Path(
                logo
            ).exists()
        ):
            st.image(
                logo,
                width=logo_width,
            )

    with text_col:
        st.markdown(
            (
                f"<div style='"
                f"border-left: 5px solid {color}; "
                "padding-left: 14px; "
                "padding-top: 2px; "
                "padding-bottom: 2px;"
                "'>"
                f"<div style='font-size: 1.55rem; "
                "font-weight: 700; line-height: 1.15;'>"
                f"{html.escape(metadata.get('name', ''))}"
                "</div>"
                f"<div style='font-size: 0.92rem; "
                "opacity: 0.70; margin-top: 4px;'>"
                f"{html.escape(subtitle or '')}"
                "</div>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )





@st.cache_data(
    show_spinner=False,
)
def cached_team_season_intelligence(
    season,
):
    summary_path = (
        ROOT_DIR
        / "results"
        / "season_intelligence"
        / f"{season}_team_summary_v1.csv"
    )

    history_path = (
        ROOT_DIR
        / "results"
        / "season_intelligence"
        / f"{season}_team_rating_games_v1.csv"
    )

    if not summary_path.exists():
        raise FileNotFoundError(
            "Missing Team Season Intelligence summary: "
            f"{summary_path}"
        )

    if not history_path.exists():
        raise FileNotFoundError(
            "Missing Team Season Intelligence history: "
            f"{history_path}"
        )

    summary = pd.read_csv(
        summary_path,
    )

    history = pd.read_csv(
        history_path,
        dtype={
            "gameId": str,
        },
    )

    history[
        "gameDate"
    ] = pd.to_datetime(
        history[
            "gameDate"
        ],
        errors="coerce",
    )

    if history[
        "gameDate"
    ].isna().any():
        raise ValueError(
            "Invalid gameDate in Team Season Intelligence history."
        )

    return (
        summary,
        history,
    )





def add_historical_league_ranks(
    history,
):
    """
    Attach each team's league rank immediately after
    every game using the frozen Courtvision ratings.

    This is display-only and does not recompute or
    modify rating updates.
    """

    ranked = history.copy()

    ranked[
        "_sortDate"
    ] = pd.to_datetime(
        ranked[
            "gameDate"
        ],
        errors="coerce",
    )

    if ranked[
        "_sortDate"
    ].isna().any():
        raise ValueError(
            "Invalid gameDate while computing league ranks."
        )

    ranked = (
        ranked
        .sort_values(
            [
                "_sortDate",
                "gameId",
                "team",
            ],
            kind="mergesort",
        )
        .reset_index(
            drop=True
        )
    )

    teams = sorted(
        ranked[
            "team"
        ]
        .dropna()
        .unique()
        .tolist()
    )

    current_ratings = {
        team:
            1500.0

        for team in teams
    }

    rank_by_row = {}

    for (
        game_date,
        game_id,
    ), game_rows in ranked.groupby(
        [
            "_sortDate",
            "gameId",
        ],
        sort=False,
    ):
        for row_index, row in (
            game_rows.iterrows()
        ):
            current_ratings[
                str(
                    row[
                        "team"
                    ]
                )
            ] = float(
                row[
                    "ratingAfter"
                ]
            )

        rating_series = pd.Series(
            current_ratings,
            dtype=float,
        )

        league_ranks = (
            rating_series
            .rank(
                method="min",
                ascending=False,
            )
            .astype(
                int
            )
        )

        for row_index, row in (
            game_rows.iterrows()
        ):
            team = str(
                row[
                    "team"
                ]
            )

            rank_by_row[
                row_index
            ] = int(
                league_ranks[
                    team
                ]
            )

    ranked[
        "leagueRankAfterGame"
    ] = (
        ranked.index
        .map(
            rank_by_row
        )
        .astype(
            int
        )
    )

    ranked = (
        ranked
        .drop(
            columns=[
                "_sortDate",
            ]
        )
    )

    return ranked





def render_historical_team_rating(
    game_id,
    season,
    home_team_metadata,
    away_team_metadata,
):
    """
    Render frozen Team Courtvision Rating context for one
    historical game.

    This is display-only. It reads the already-generated
    Season Intelligence artifacts and does not recompute
    rating updates.
    """

    try:
        _, history = (
            cached_team_season_intelligence(
                season
            )
        )

    except FileNotFoundError:
        # Some historical seasons may not have Courtvision
        # Rating artifacts. Historical game analysis should
        # still render normally.
        return

    except Exception as error:
        st.warning(
            "Team Courtvision Rating context could not be "
            f"loaded: {error}"
        )
        return

    history = (
        add_historical_league_ranks(
            history
        )
    )

    normalized_game_id = (
        str(
            game_id
        )
        .zfill(
            10
        )
    )

    normalized_history_ids = (
        history[
            "gameId"
        ]
        .astype(
            str
        )
        .str.zfill(
            10
        )
    )

    game_rows = (
        history.loc[
            normalized_history_ids
            == normalized_game_id
        ]
        .copy()
    )

    if len(
        game_rows
    ) != 2:
        return

    game_rows = (
        game_rows
        .sort_values(
            "isHome",
            ascending=False,
        )
        .reset_index(
            drop=True
        )
    )

    home_row = (
        game_rows.loc[
            game_rows[
                "isHome"
            ]
            == 1
        ]
        .iloc[
            0
        ]
    )

    away_row = (
        game_rows.loc[
            game_rows[
                "isHome"
            ]
            == 0
        ]
        .iloc[
            0
        ]
    )

    winner_row = (
        game_rows.loc[
            game_rows[
                "teamWin"
            ]
            == 1
        ]
        .iloc[
            0
        ]
    )

    st.subheader(
        "Team Courtvision Rating"
    )

    st.caption(
        (
            f"{season} · Frozen Team Courtvision Rating v1 · "
            "ratings shown immediately before and after this game"
        )
    )

    def render_team_rating_card(
        row,
        location_label,
    ):
        team = str(
            row[
                "team"
            ]
        )

        if (
            team
            == home_team_metadata.get(
                "tricode"
            )
        ):
            metadata = (
                home_team_metadata
            )

        elif (
            team
            == away_team_metadata.get(
                "tricode"
            )
        ):
            metadata = (
                away_team_metadata
            )

        else:
            metadata = (
                get_team_metadata_by_tricode(
                    team
                )
            )

        team_name = metadata.get(
            "name",
            team,
        )

        team_color = metadata.get(
            "chart_color",
            "#58A6FF",
        )

        logo = metadata.get(
            "logo"
        )

        rating_before = float(
            row[
                "ratingBefore"
            ]
        )

        rating_after = float(
            row[
                "ratingAfter"
            ]
        )

        rating_change = float(
            row[
                "ratingChange"
            ]
        )

        pregame_probability = float(
            row[
                "pregameWinProbability"
            ]
        )

        league_rank = int(
            row[
                "leagueRankAfterGame"
            ]
        )

        result_label = (
            "W"
            if int(
                row[
                    "teamWin"
                ]
            )
            == 1
            else "L"
        )

        change_color = (
            "#2ECC71"
            if rating_change >= 0
            else "#FF5C77"
        )

        card = st.container(
            border=True,
        )

        with card:
            st.markdown(
                (
                    "<div style='"
                    f"height:4px; background:{team_color}; "
                    "border-radius:999px; margin-bottom:12px;"
                    "'></div>"
                ),
                unsafe_allow_html=True,
            )

            identity_logo_col, identity_text_col = (
                st.columns(
                    [
                        1,
                        5,
                    ],
                    vertical_alignment="center",
                )
            )

            with identity_logo_col:
                if (
                    logo
                    and Path(
                        logo
                    ).exists()
                ):
                    st.image(
                        logo,
                        width=52,
                    )

            with identity_text_col:
                st.markdown(
                    (
                        f"### {html.escape(team_name)}"
                        "  \n"
                        f"{location_label} · {result_label}"
                    )
                )

            metric_1, metric_2, metric_3 = (
                st.columns(
                    3
                )
            )

            with metric_1:
                st.metric(
                    "Pregame",
                    f"{rating_before:.1f}",
                )

            with metric_2:
                st.markdown(
                    (
                        "<div style='"
                        "font-size:0.82rem; opacity:0.68; "
                        "margin-bottom:0.25rem;"
                        "'>"
                        "Rating Change"
                        "</div>"
                        "<div style='"
                        "font-size:1.75rem; "
                        "font-weight:700; "
                        f"color:{change_color};"
                        "'>"
                        f"{rating_change:+.1f}"
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )

            with metric_3:
                st.metric(
                    "Postgame",
                    f"{rating_after:.1f}",
                )

            st.caption(
                (
                    f"Pregame win expectation: "
                    f"{pregame_probability * 100.0:.1f}% "
                    f"· Postgame league rank: #{league_rank}"
                )
            )

    away_col, home_col = (
        st.columns(
            2
        )
    )

    with away_col:
        render_team_rating_card(
            away_row,
            "Away",
        )

    with home_col:
        render_team_rating_card(
            home_row,
            "Home",
        )

    margin_dominance = float(
        winner_row[
            "marginDominance"
        ]
    )

    dominance_multiplier = float(
        winner_row[
            "dominanceMultiplier"
        ]
    )

    winner_margin = abs(
        float(
            winner_row[
                "signedMargin"
            ]
        )
    )

    detail_1, detail_2, detail_3 = (
        st.columns(
            3
        )
    )

    with detail_1:
        st.metric(
            "Final Margin",
            f"{winner_margin:.0f}",
        )

    with detail_2:
        st.metric(
            "Margin Dominance",
            f"{margin_dominance:.3f}",
        )

    with detail_3:
        st.metric(
            "Dominance Multiplier",
            f"{dominance_multiplier:.3f}×",
        )

    st.markdown(
        "#### Why Did the Ratings Move?"
    )

    winner_metadata = (
        get_team_metadata_by_tricode(
            winner_row[
                "team"
            ]
        )
    )

    winner_color = (
        winner_metadata.get(
            "chart_color",
            "#58A6FF",
        )
    )

    explanation = (
        build_rating_change_explanation(
            winner_row
        )
    )

    st.markdown(
        (
            "<div style='"
            "padding:14px 16px; "
            "border-radius:10px; "
            "background:rgba(148,163,184,0.06); "
            f"border-left:4px solid {winner_color};"
            "'>"
            f"{html.escape(explanation)}"
            "</div>"
        ),
        unsafe_allow_html=True,
    )

    st.caption(
        (
            "Courtvision Rating updates are zero-sum, so the "
            "opponent receives the equal and opposite rating change."
        )
    )





def format_signed_rating(
    value,
):
    return (
        f"{float(value):+.1f}"
    )





def render_season_intelligence(
    season,
):
    try:
        summary, history = (
            cached_team_season_intelligence(
                season
            )
        )

        history = (
            add_historical_league_ranks(
                history
            )
        )

    except Exception as error:
        st.error(
            "Could not load Season Intelligence: "
            f"{error}"
        )
        return



    st.subheader(
        "Season Intelligence"
    )

    st.caption(
        (
            f"{season} regular season · "
            "Team Courtvision Rating v1"
        )
    )



    # --------------------------------------------------------
    # League leader
    # --------------------------------------------------------

    leader = (
        summary
        .sort_values(
            "ratingRank"
        )
        .iloc[
            0
        ]
    )

    leader_metadata = (
        get_team_metadata_by_tricode(
            leader[
                "team"
            ]
        )
    )

    leader_color = (
        leader_metadata.get(
            "chart_color",
            "#58A6FF",
        )
    )

    st.markdown(
        (
            "<div style='"
            f"height: 5px; background: {leader_color}; "
            "border-radius: 999px; margin-bottom: 14px;"
            "'></div>"
        ),
        unsafe_allow_html=True,
    )

    render_season_team_identity(
        leader_metadata,
        subtitle=(
            f"No. 1 Team · "
            f"{int(leader['wins'])}-"
            f"{int(leader['losses'])}"
        ),
        logo_width=78,
    )

    leader_col_1, leader_col_2, leader_col_3 = (
        st.columns(
            3
        )
    )

    with leader_col_1:
        st.metric(
            "Courtvision Rating",
            f"{leader['currentRating']:.1f}",
            delta=(
                f"{leader['seasonRatingChange']:+.1f} "
                "this season"
            ),
        )

    with leader_col_2:
        st.metric(
            "Last 5",
            format_signed_rating(
                leader[
                    "last5RatingChange"
                ]
            ),
        )

    with leader_col_3:
        st.metric(
            "Last 10",
            format_signed_rating(
                leader[
                    "last10RatingChange"
                ]
            ),
        )



    st.divider()



    # --------------------------------------------------------
    # League leaderboard
    # --------------------------------------------------------

    st.markdown(
        "### Team Ratings"
    )

    leaderboard = (
        summary[
            [
                "ratingRank",
                "team",
                "wins",
                "losses",
                "currentRating",
                "last5RatingChange",
                "last10RatingChange",
                "seasonRatingChange",
            ]
        ]
        .copy()
    )

    leaderboard[
        "Record"
    ] = (
        leaderboard[
            "wins"
        ]
        .astype(
            int
        )
        .astype(
            str
        )
        + "-"
        + leaderboard[
            "losses"
        ]
        .astype(
            int
        )
        .astype(
            str
        )
    )

    leaderboard = (
        leaderboard
        .rename(
            columns={
                "ratingRank":
                    "Rank",

                "team":
                    "Team",

                "currentRating":
                    "Rating",

                "last5RatingChange":
                    "Last 5",

                "last10RatingChange":
                    "Last 10",

                "seasonRatingChange":
                    "Season Δ",
            }
        )
        [
            [
                "Rank",
                "Team",
                "Record",
                "Rating",
                "Last 5",
                "Last 10",
                "Season Δ",
            ]
        ]
    )

    def style_leaderboard_row(
        row,
    ):
        styles = [
            ""
            for _ in row.index
        ]

        rank = int(
            row[
                "Rank"
            ]
        )

        if rank == 1:
            background = (
                "background-color: rgba(255, 215, 0, 0.08);"
            )

        elif rank <= 3:
            background = (
                "background-color: rgba(148, 163, 184, 0.06);"
            )

        else:
            background = ""

        if background:
            styles = [
                background
                for _ in row.index
            ]

        return styles



    def movement_style(
        value,
    ):
        try:
            numeric = float(
                str(
                    value
                )
                .replace(
                    "+",
                    "",
                )
            )

        except Exception:
            return ""

        if numeric > 0:
            return (
                "color: #2ECC71; "
                "font-weight: 600;"
            )

        if numeric < 0:
            return (
                "color: #FF5C77; "
                "font-weight: 600;"
            )

        return ""



    leaderboard_display = (
        leaderboard
        .copy()
    )

    for column in [
        "Last 5",
        "Last 10",
        "Season Δ",
    ]:
        leaderboard_display[
            column
        ] = (
            leaderboard_display[
                column
            ]
            .map(
                lambda value:
                    f"{float(value):+.1f}"
            )
        )

    leaderboard_display[
        "Rating"
    ] = (
        leaderboard_display[
            "Rating"
        ]
        .map(
            lambda value:
                f"{float(value):.1f}"
        )
    )

    leaderboard_styled = (
        leaderboard_display
        .style
        .apply(
            style_leaderboard_row,
            axis=1,
        )
        .map(
            movement_style,
            subset=[
                "Last 5",
                "Last 10",
                "Season Δ",
            ],
        )
        .set_properties(
            subset=[
                "Rating",
            ],
            **{
                "font-weight":
                    "700",
            },
        )
        .set_properties(
            subset=[
                "Rank",
            ],
            **{
                "font-weight":
                    "700",
                "color":
                    "#AAB2C0",
            },
        )
    )

    st.dataframe(
        leaderboard_styled,
        hide_index=True,
        width="stretch",
        height=510,
    )



    # --------------------------------------------------------
    # Recent form
    # --------------------------------------------------------

    st.markdown(
        "### Recent Form"
    )

    riser_col, faller_col = (
        st.columns(
            2
        )
    )

    risers = (
        summary
        .sort_values(
            "last5RatingChange",
            ascending=False,
        )
        .head(
            5
        )
        [
            [
                "team",
                "last5RatingChange",
            ]
        ]
        .rename(
            columns={
                "team":
                    "Team",

                "last5RatingChange":
                    "Last 5",
            }
        )
    )

    fallers = (
        summary
        .sort_values(
            "last5RatingChange",
            ascending=True,
        )
        .head(
            5
        )
        [
            [
                "team",
                "last5RatingChange",
            ]
        ]
        .rename(
            columns={
                "team":
                    "Team",

                "last5RatingChange":
                    "Last 5",
            }
        )
    )

    risers[
        "Rating Δ"
    ] = (
        risers[
            "Last 5"
        ]
        .map(
            lambda value:
                f"{float(value):+.1f}"
        )
    )

    risers = risers[
        [
            "Team",
            "Rating Δ",
        ]
    ]

    fallers[
        "Rating Δ"
    ] = (
        fallers[
            "Last 5"
        ]
        .map(
            lambda value:
                f"{float(value):+.1f}"
        )
    )

    fallers = fallers[
        [
            "Team",
            "Rating Δ",
        ]
    ]

    with riser_col:
        st.markdown(
            "**Biggest Risers — Last 5 Games**"
        )

        for _, row in (
            risers.iterrows()
        ):
            render_recent_form_team(
                row[
                    "Team"
                ],
                row[
                    "Rating Δ"
                ],
            )

    with faller_col:
        st.markdown(
            "**Biggest Fallers — Last 5 Games**"
        )

        for _, row in (
            fallers.iterrows()
        ):
            render_recent_form_team(
                row[
                    "Team"
                ],
                row[
                    "Rating Δ"
                ],
            )



    st.divider()



    # --------------------------------------------------------
    # Team detail
    # --------------------------------------------------------

    st.markdown(
        "### Team Detail"
    )

    team_options = (
        summary
        .sort_values(
            "ratingRank"
        )[
            "team"
        ]
        .tolist()
    )

    selected_team = (
        st.selectbox(
            "Team",
            team_options,
            key=(
                "courtvision_season_intelligence_team"
            ),
        )
    )

    team_summary = (
        summary.loc[
            summary[
                "team"
            ]
            == selected_team
        ]
        .iloc[
            0
        ]
    )

    selected_team_metadata = (
        get_team_metadata_by_tricode(
            selected_team
        )
    )

    selected_team_color = (
        selected_team_metadata.get(
            "chart_color",
            "#58A6FF",
        )
    )

    selected_team_secondary = (
        selected_team_metadata.get(
            "secondary_color",
            selected_team_color,
        )
    )

    st.markdown(
        (
            "<div style='"
            f"height: 5px; background: linear-gradient("
            f"90deg, {selected_team_color}, "
            f"{selected_team_secondary}); "
            "border-radius: 999px; margin: 8px 0 14px 0;"
            "'></div>"
        ),
        unsafe_allow_html=True,
    )

    render_season_team_identity(
        selected_team_metadata,
        subtitle=(
            f"#{int(team_summary['ratingRank'])} in NBA · "
            f"{int(team_summary['wins'])}-"
            f"{int(team_summary['losses'])}"
        ),
        logo_width=82,
    )



    team_games = (
        history.loc[
            history[
                "team"
            ]
            == selected_team
        ]
        .sort_values(
            [
                "gameDate",
                "teamGameNumber",
            ],
            kind="mergesort",
        )
        .reset_index(
            drop=True
        )
    )



    peak_rank = int(
        team_games[
            "leagueRankAfterGame"
        ].min()
    )

    lowest_rank = int(
        team_games[
            "leagueRankAfterGame"
        ].max()
    )

    metric_col_1, metric_col_2, metric_col_3, metric_col_4 = (
        st.columns(
            4
        )
    )

    with metric_col_1:
        st.metric(
            "Current Rating",
            f"{team_summary['currentRating']:.1f}",
            help=(
                f"Current NBA rank: "
                f"#{int(team_summary['ratingRank'])}"
            ),
        )

    with metric_col_2:
        st.metric(
            "Peak Rating",
            f"{team_summary['peakRating']:.1f}",
            help=(
                f"Best league rank reached after a game: "
                f"#{peak_rank}"
            ),
        )

    with metric_col_3:
        st.metric(
            "Lowest Rating",
            f"{team_summary['lowestRating']:.1f}",
            help=(
                f"Worst league rank reached after a game: "
                f"#{lowest_rank}"
            ),
        )

    with metric_col_4:
        st.metric(
            "Season Change",
            format_signed_rating(
                team_summary[
                    "seasonRatingChange"
                ]
            ),
        )



    # --------------------------------------------------------
    # Rating history chart
    # --------------------------------------------------------

    chart = go.Figure()

    team_games[
        "resultLabel"
    ] = np.where(
        team_games[
            "teamWin"
        ]
        == 1,
        "W",
        "L",
    )

    chart.add_trace(
        go.Scatter(
            x=team_games[
                "gameDate"
            ],

            y=team_games[
                "ratingAfter"
            ],

            mode="lines+markers",

            name=selected_team,

            line={
                "color":
                    selected_team_color,

                "width":
                    3,
            },

            marker={
                "color":
                    selected_team_color,

                "size":
                    6,

                "line": {
                    "width":
                        1,

                    "color":
                        selected_team_secondary,
                },
            },

            customdata=np.column_stack(
                [
                    team_games[
                        "opponent"
                    ],

                    team_games[
                        "resultLabel"
                    ],

                    team_games[
                        "ratingChange"
                    ],

                    team_games[
                        "leagueRankAfterGame"
                    ],
                ]
            ),

            hovertemplate=(
                "Rating: %{y:.1f}"
                "<br>Opponent: %{customdata[0]}"
                "<br>Result: %{customdata[1]}"
                "<br>League Rank: #%{customdata[3]}"
                "<br>Change: %{customdata[2]:+.1f}"
                "<extra></extra>"
            ),
        )
    )

    chart.add_hline(
        y=1500.0,
        line_dash="dash",
        opacity=0.45,
        annotation_text="League baseline",
        annotation_position="bottom right",
    )

    chart.update_layout(
        title=(
            f"{selected_team_metadata['name']} "
            "Courtvision Rating"
        ),

        xaxis_title=None,

        yaxis_title="Rating",

        hovermode="x unified",

        height=430,

        margin={
            "l": 20,
            "r": 20,
            "t": 55,
            "b": 20,
        },
    )

    st.plotly_chart(
        chart,
        width="stretch",
    )



    # --------------------------------------------------------
    # Form + per-game impact
    # --------------------------------------------------------

    detail_col_1, detail_col_2, detail_col_3, detail_col_4 = (
        st.columns(
            4
        )
    )

    with detail_col_1:
        st.metric(
            "Last 5",
            format_signed_rating(
                team_summary[
                    "last5RatingChange"
                ]
            ),
        )

    with detail_col_2:
        st.metric(
            "Last 10",
            format_signed_rating(
                team_summary[
                    "last10RatingChange"
                ]
            ),
        )

    with detail_col_3:
        st.metric(
            "Biggest Gain",
            format_signed_rating(
                team_summary[
                    "largestSingleGameGain"
                ]
            ),
        )

    with detail_col_4:
        st.metric(
            "Biggest Loss",
            format_signed_rating(
                team_summary[
                    "largestSingleGameLoss"
                ]
            ),
        )



    # --------------------------------------------------------
    # Recent games
    # --------------------------------------------------------

    st.markdown(
        "#### Recent Rating Changes"
    )

    recent_games = (
        team_games
        .tail(
            10
        )
        .sort_values(
            "gameDate",
            ascending=False,
        )
        .copy()
    )

    recent_games[
        "Result"
    ] = np.where(
        recent_games[
            "teamWin"
        ]
        == 1,
        "W",
        "L",
    )

    recent_games[
        "Date"
    ] = (
        recent_games[
            "gameDate"
        ]
        .dt.strftime(
            "%b %d, %Y"
        )
    )

    recent_games = (
        recent_games
        .rename(
            columns={
                "opponent":
                    "Opponent",

                "ratingChange":
                    "Rating Δ",

                "ratingAfter":
                    "Rating",

                "leagueRankAfterGame":
                    "Rank",
            }
        )
        [
            [
                "Date",
                "Opponent",
                "Result",
                "Rating Δ",
                "Rating",
                "Rank",
            ]
        ]
    )

    recent_games[
        "Rating Δ"
    ] = (
        recent_games[
            "Rating Δ"
        ]
        .map(
            lambda value:
                f"{float(value):+.1f}"
        )
    )

    recent_games[
        "Rating"
    ] = (
        recent_games[
            "Rating"
        ]
        .map(
            lambda value:
                f"{float(value):.1f}"
        )
    )

    recent_games[
        "Rank"
    ] = (
        recent_games[
            "Rank"
        ]
        .map(
            lambda value:
                f"#{int(value)}"
        )
    )


    recent_games_styled = (
        recent_games
        .style
        .map(
            lambda value:
                (
                    "color: #2ECC71; "
                    "font-weight: 700;"
                )
                if value == "W"
                else (
                    "color: #FF5C77; "
                    "font-weight: 700;"
                ),
            subset=[
                "Result",
            ],
        )
        .map(
            movement_style,
            subset=[
                "Rating Δ",
            ],
        )
        .set_properties(
            subset=[
                "Rating",
            ],
            **{
                "font-weight":
                    "700",
            },
        )
        .set_properties(
            subset=[
                "Rank",
            ],
            **{
                "font-weight":
                    "700",
                "color":
                    "#AAB2C0",
            },
        )
        .set_properties(
            subset=[
                "Date",
            ],
            **{
                "color":
                    "#AAB2C0",
            },
        )
    )

    st.dataframe(
        recent_games_styled,
        hide_index=True,
        width="stretch",
        height=390,
    )



    # --------------------------------------------------------
    # Explain a rating change
    # --------------------------------------------------------

    st.markdown(
        "#### Why Did the Rating Change?"
    )

    explanation_games = (
        team_games
        .tail(
            10
        )
        .sort_values(
            "gameDate",
            ascending=False,
        )
        .copy()
    )

    explanation_games[
        "explanationLabel"
    ] = (
        explanation_games.apply(
            lambda row:
                (
                    f"{row['gameDate'].strftime('%b %d')} · "
                    f"{'W' if int(row['teamWin']) == 1 else 'L'} "
                    f"vs {row['opponent']} · "
                    f"{float(row['ratingChange']):+.1f}"
                ),
            axis=1,
        )
    )

    explanation_labels = (
        explanation_games[
            "explanationLabel"
        ].tolist()
    )

    selected_explanation_label = (
        st.selectbox(
            "Game",
            explanation_labels,
            key=(
                "courtvision_rating_explanation_game_"
                f"{season}_{selected_team}"
            ),
            label_visibility="collapsed",
        )
    )

    explanation_row = (
        explanation_games.loc[
            explanation_games[
                "explanationLabel"
            ]
            == selected_explanation_label
        ]
        .iloc[
            0
        ]
    )

    opponent_metadata = (
        get_team_metadata_by_tricode(
            explanation_row[
                "opponent"
            ]
        )
    )

    result_is_win = (
        int(
            explanation_row[
                "teamWin"
            ]
        )
        == 1
    )

    explanation_color = (
        "#2ECC71"
        if result_is_win
        else "#FF5C77"
    )

    explanation_container = (
        st.container(
            border=True,
        )
    )

    with explanation_container:

        logo_col, matchup_col, delta_col = (
            st.columns(
                [
                    1,
                    6,
                    2,
                ],
                vertical_alignment="center",
            )
        )

        with logo_col:
            opponent_logo = (
                opponent_metadata.get(
                    "logo"
                )
            )

            if (
                opponent_logo
                and Path(
                    opponent_logo
                ).exists()
            ):
                st.image(
                    opponent_logo,
                    width=48,
                )

        with matchup_col:
            st.markdown(
                (
                    f"**{'Win' if result_is_win else 'Loss'} "
                    f"vs {explanation_row['opponent']}**  "
                    f"· "
                    f"{explanation_row['gameDate'].strftime('%b %d, %Y')}"
                )
            )

            st.caption(
                (
                    f"Pregame expectation: "
                    f"{float(explanation_row['pregameWinProbability']) * 100.0:.1f}% "
                    f"· Opponent rating: "
                    f"{float(explanation_row['opponentRatingBefore']):.1f} "
                    f"· Margin: "
                    f"{abs(float(explanation_row['signedMargin'])):.0f}"
                )
            )

        with delta_col:
            st.markdown(
                (
                    "<div style='"
                    "text-align:right; "
                    "font-size:1.45rem; "
                    "font-weight:750; "
                    f"color:{explanation_color};"
                    "'>"
                    f"{float(explanation_row['ratingChange']):+.1f}"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )

            st.caption(
                "rating points"
            )

        st.markdown(
            (
                "<div style='"
                "margin-top: 8px; "
                "padding: 12px 14px; "
                "border-radius: 10px; "
                "background: rgba(148, 163, 184, 0.06); "
                f"border-left: 4px solid {selected_team_color};"
                "'>"
                f"{html.escape(build_rating_change_explanation(explanation_row))}"
                "</div>"
            ),
            unsafe_allow_html=True,
        )





def run_season_intelligence():

    render_season_intelligence(
        season
    )





def run_historical():

    if not st.session_state[

        "courtvision_active"

    ]:

        st.info(

            "Choose a season, date, "

            "and game, then click "

            "**Analyze Game**."

        )

        return



    try:

        with st.spinner(

            "Running Courtvision analysis..."

        ):

            result = cached_historical_analysis(

                game_id=selected_game_id,

                season=season,

                game_date=selected_date,

                top_k=3,

            )



    except Exception as error:

        st.error(

            "Could not analyze game: "

            f"{error}"

        )

        return



    render_game(

        result,

        game_id=selected_game_id,

        season=season,

        live=False,

    )





# ============================================================

# Live

# ============================================================



def run_live_once():

    if not st.session_state[

        "courtvision_active"

    ]:

        st.info(

            "Choose a live game and "

            "click **Analyze Game**."

        )

        return



    try:

        with st.spinner(

            "Fetching latest game state..."

        ):

            result = analyze_live_game(

                game_id=selected_game_id,

                season=season,

                game_date=selected_date,

                top_k=3,

                assume_final=False,

            )



    except Exception as error:

        st.error(

            "Could not fetch game: "

            f"{error}"

        )

        return



    render_game(

        result,

        game_id=selected_game_id,

        season=season,

        live=True,

    )





# ============================================================

# Execute

# ============================================================



if mode == "Historical":

    run_historical()



elif mode == "Live":

    if auto_refresh:

        interval = (

            f"{refresh_seconds}s"

        )



        @st.fragment(

            run_every=interval

        )

        def live_fragment():

            run_live_once()



        live_fragment()



    else:

        run_live_once()



else:

    run_season_intelligence()
