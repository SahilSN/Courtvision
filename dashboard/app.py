import html
import pandas as pd
import sys

from datetime import date
from nba_api.stats.static import players as nba_players
from pathlib import Path



import plotly.graph_objects as go

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


from box_score import (
    fetch_box_score,
    get_team_players,
)


from game_catalog import (

    fetch_games_for_date,

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

    ttl=300

)

def cached_games_for_date(

    season,

    selected_date,

):

    return (

        fetch_games_for_date(

            season=season,

            game_date=(

                selected_date

            ),

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


@st.cache_data(

    show_spinner=False,

)

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

    "Game Selection"

)





mode = st.sidebar.radio(

    "Mode",

    [

        "Historical",

        "Live",

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



else:



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

# Analyze button

# ============================================================



analyze_button = st.sidebar.button(

    "Analyze Game",

    type="primary",

    disabled=(

        selected_game_id

        is None

    ),

    key="courtvision_analyze_game",

)





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

        "Counterfactual Win Probability "

        "Added (WPA v3). Positive WPA means "

        "the player's attributed events "

        "increased their team's modeled "

        "chance of winning. Current WPA uses "

        "primary-event attribution; assist and "

        "shared-credit attribution will be "

        "reflected here when that layer is added."

    )



    if live:

        st.info(

            "Player WPA is currently shown for "

            "completed historical games. Live WPA "

            "will be enabled once the live player-"

            "impact pipeline is validated."

        )

        return



    try:

        impact = (

            cached_player_impact(

                str(game_id),

                season,

                "v3",

            )

        )



    except Exception as error:

        st.info(

            "Player impact is not "

            "available for this game."

        )



        with st.expander(

            "Player impact details"

        ):

            st.code(

                str(error)

            )



        return



    summary = (

        impact[

            "player_summary"

        ]

    )



    home_team = (

        impact[

            "home_team"

        ]

    )



    away_team = (

        impact[

            "away_team"

        ]

    )



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



    home_color = home_team_metadata.get(

        "chart_color",

        "#58A6FF",

    )



    away_color = away_team_metadata.get(

        "chart_color",

        "#FF5C77",

    )



    home_col, away_col = (

        st.columns(2)

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





# ============================================================

# Renderer

# ============================================================




# ============================================================
# Box score
# ============================================================

@st.cache_data(
    ttl=86400,
    show_spinner=False,
)
def cached_historical_box_score(
    game_id,
):
    return fetch_box_score(
        game_id
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
    Return personId -> roster position.

    Historical box-score starter rows usually contain a
    position directly, while bench rows may not. The team
    roster fills those missing bench positions.
    """

    try:
        endpoint = (
            commonteamroster
            .CommonTeamRoster(
                team_id=int(team_id),
                season=season,
                timeout=60,
            )
        )

        frames = (
            endpoint.get_data_frames()
        )

        if not frames:
            return {}

        roster_df = (
            frames[0]
            .copy()
        )

        positions = {}

        for _, row in (
            roster_df.iterrows()
        ):
            player_id = (
                row.get(
                    "PLAYER_ID"
                )
            )

            if (
                player_id is None
                or player_id != player_id
            ):
                continue

            positions[
                int(player_id)
            ] = (
                normalize_box_position(
                    row.get(
                        "POSITION"
                    )
                )
            )

        return positions

    except Exception:
        # Position information is supplemental.
        # Never make the box score fail because this
        # secondary endpoint is unavailable.
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

        # If both the box-score row and the team roster
        # are missing a position, query the player's
        # canonical NBA profile as a final fallback.
        if (
            position == "—"
            and person_id is not None
        ):
            try:
                if person_id == person_id:
                    position = (
                        cached_player_position(
                            int(
                                person_id
                            )
                        )
                    )

            except (
                TypeError,
                ValueError,
            ):
                pass

        # If both the box-score row and the team roster
        # are missing a position, query the player's
        # canonical NBA profile as a final fallback.
        if (
            position == "—"
            and person_id is not None
        ):
            try:
                if person_id == person_id:
                    position = (
                        cached_player_position(
                            int(
                                person_id
                            )
                        )
                    )

            except (
                TypeError,
                ValueError,
            ):
                pass

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
        detect_momentum_runs(
            game_df,
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
            top_k=3,
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
            f"Last Live "
            f"{home_team['tricode']} "
            "Win Probability"
        )

        away_label = (
            f"Last Live "
            f"{away_team['tricode']} "
            "Win Probability"
        )

    with home_metric:
        st.metric(
            home_label,
            f"{current_home_wp:.1%}",
        )

    with away_metric:
        st.metric(
            away_label,
            f"{current_away_wp:.1%}",
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
            "Last Live Win Probability is Courtvision's "
            "model estimate at the final game state before "
            "the known final result is applied."
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

            f"## "

            f"{home_team['tricode']} "

            "Turning Points"

        )



        for _, row in (

            home_swings.iterrows()

        ):

            render_swing_card(

                row,

                home_team,

                "home",

            )





    with away_column:

        st.markdown(

            f"## "

            f"{away_team['tricode']} "

            "Turning Points"

        )



        for _, row in (

            away_swings.iterrows()

        ):

            render_swing_card(

                row,

                away_team,

                "away",

            )



    st.divider()



    render_momentum_runs(
        game_df,
        home_team,
        away_team,
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

    render_player_impact(

        game_id=game_id,

        season=season,

        home_team_metadata=home_team,

        away_team_metadata=away_team,

        live=live,

    )





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

            result = analyze_live_game(

                game_id=selected_game_id,

                season=season,

                game_date=selected_date,

                top_k=3,

                assume_final=True,

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



else:

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
