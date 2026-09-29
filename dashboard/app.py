import html
import sys
from datetime import date
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st


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

from game_catalog import (
    fetch_games_for_date,
)

from live_analysis import (
    analyze_live_game,
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
        index=1,
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

def build_win_probability_plot(
    game_df,
    home_swings,
    away_swings,
    home_team,
    away_team,
):
    home_color = (
        home_team.get(
            "chart_color",
            "#58A6FF",
        )
    )

    away_color = (
        away_team.get(
            "chart_color",
            "#FF5C77",
        )
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


    fig = (
        go.Figure()
    )


    fig.add_trace(
        go.Scatter(
            x=(
                model_game_df[
                    "elapsedGameTime"
                ]
            ),

            y=(
                model_game_df[
                    "winProbability"
                ]
                * 100
            ),

            mode="lines",

            line={
                "color":
                    home_color,

                "width":
                    4,
            },

            name=(
                f"{home_team['tricode']} "
                "win probability"
            ),

            hovertemplate=(
                "<b>"
                f"{home_team['tricode']}"
                "</b><br>"
                "Win probability: "
                "%{y:.1f}%"
                "<extra></extra>"
            ),
        )
    )


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
        text="Toss-up",
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


    if not home_swings.empty:
        row = (
            home_swings.iloc[0]
        )

        change = (
            row[
                "probabilityChange"
            ]
            * 100
        )

        clock = (
            normalize_clock_display(
                row.get(
                    "clock"
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
                    row[
                        "winProbability"
                    ]
                    * 100
                ],

                mode="markers",

                marker={
                    "size":
                        13,

                    "color":
                        home_color,

                    "line": {
                        "color":
                            "#FFFFFF",

                        "width":
                            2,
                    },
                },

                name=(
                    f"{home_team['tricode']} "
                    "biggest swing"
                ),

                hovertemplate=(
                    "<b>"
                    f"{home_team['tricode']} "
                    f"{change:+.1f} pp"
                    "</b><br>"
                    f"Q{int(row['period'])} "
                    f"{clock}<br>"
                    f"{row.get('description', '')}"
                    "<extra></extra>"
                ),
            )
        )


    if not away_swings.empty:
        row = (
            away_swings.iloc[0]
        )

        change = (
            row[
                "probabilityChange"
            ]
            * 100
        )

        clock = (
            normalize_clock_display(
                row.get(
                    "clock"
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
                    row[
                        "winProbability"
                    ]
                    * 100
                ],

                mode="markers",

                marker={
                    "size":
                        13,

                    "color":
                        away_color,

                    "line": {
                        "color":
                            "#FFFFFF",

                        "width":
                            2,
                    },
                },

                name=(
                    f"{away_team['tricode']} "
                    "biggest swing"
                ),

                hovertemplate=(
                    "<b>"
                    f"{away_team['tricode']} "
                    f"{change:+.1f} pp"
                    "</b><br>"
                    f"Q{int(row['period'])} "
                    f"{clock}<br>"
                    f"{row.get('description', '')}"
                    "<extra></extra>"
                ),
            )
        )


    if not terminal_df.empty:
        last_model_row = (
            model_game_df
            .iloc[-1]
        )

        terminal_row = (
            terminal_df
            .iloc[-1]
        )

        last_model_time = float(
            last_model_row[
                "elapsedGameTime"
            ]
        )

        last_probability = (
            float(
                last_model_row[
                    "winProbability"
                ]
            )
            * 100
        )

        final_time = float(
            terminal_row[
                "elapsedGameTime"
            ]
        )

        final_probability = (
            float(
                terminal_row[
                    "winProbability"
                ]
            )
            * 100
        )

        fig.add_trace(
            go.Scatter(
                x=[
                    last_model_time,
                    final_time,
                ],

                y=[
                    last_probability,
                    final_probability,
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

                name=(
                    "Final result"
                ),

                hoverinfo="skip",
            )
        )

    else:
        final_time = float(
            model_game_df[
                "elapsedGameTime"
            ].max()
        )


    max_elapsed = max(
        2880.0,
        final_time,
    )


    fig.update_layout(
        title={
            "text": (
                "<b>"
                f"{home_team['tricode']} "
                "Win Probability"
                "</b><br>"
                "<span "
                "style='font-size:13px'>"
                f"vs "
                f"{away_team['tricode']}"
                "</span>"
            ),
            "x": 0.01,
            "xanchor": "left",
            "y": 0.98,
            "yanchor": "top",
        },

        height=560,

        paper_bgcolor=(
            background_color
        ),

        plot_bgcolor=(
            background_color
        ),

        font={
            "color": text_color,
            "size": 13,
        },

        # More room above the actual plot for
        # title + legend, and more right padding.
        margin={
            "l": 75,
            "r": 65,
            "t": 150,
            "b": 65,
        },

        hovermode="closest",

        legend={
            "orientation": "h",

            # Put legend in its own row above
            # the plotting region.
            "x": 0.0,
            "xanchor": "left",

            "y": 1.10,
            "yanchor": "bottom",

            "bgcolor": (
                "rgba(0,0,0,0)"
            ),
        },
    )


    fig.update_xaxes(
        # Add a small amount of horizontal
        # breathing room beyond both ends.
        range=[
            -40,
            max_elapsed + 40,
        ],

        tickvals=[
            0,
            720,
            1440,
            2160,
            2880,
        ],

        ticktext=[
            "Start",
            "Q2",
            "Q3",
            "Q4",
            "End",
        ],

        showgrid=False,
        zeroline=False,
        fixedrange=True,

        # Stops edge labels from being clipped.
        automargin=True,
    )


    fig.update_yaxes(
        title={
            "text": (
                f"{home_team['tricode']} "
                "Win Probability"
            )
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

        gridcolor=(
            grid_color
        ),

        zeroline=False,
        fixedrange=True,
        automargin=True,
    )


    return fig


# ============================================================
# Turning point cards
# ============================================================

def render_swing_card(
    row,
    team,
    direction,
):
    clock = (
        normalize_clock_display(
            row.get(
                "clock"
            )
        )
    )

    change = (
        row[
            "probabilityChange"
        ]
        * 100
    )

    before = (
        row[
            "previousWinProbability"
        ]
        * 100
    )

    after = (
        row[
            "winProbability"
        ]
        * 100
    )

    color = (
        team.get(
            "chart_color",
            "#9CA3AF",
        )
    )

    icon = (
        "▲"
        if direction
        == "home"
        else "▼"
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

    card_html = (
        f'<div class="turning-point-card" '
        f'style="border-left-color:{color};">'
        f'<div class="turning-point-change" '
        f'style="color:{color};">'
        f'{icon} {change:+.1f} pp'
        f'</div>'
        f'<div class="turning-point-clock">'
        f'Q{int(row["period"])} {clock}'
        f'</div>'
        f'<div class="turning-point-description">'
        f'{description}'
        f'</div>'
        f'<div class="turning-point-probability">'
        f'{before:.1f}% → {after:.1f}%'
        f'</div>'
        f'</div>'
    )

    st.markdown(
        card_html,
        unsafe_allow_html=True,
    )


# ============================================================
# Renderer
# ============================================================

def render_game(
    result,
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

    left, right = (
        st.columns(
            2
        )
    )


    if live:
        with left:
            st.metric(
                (
                    f"{home_team['tricode']} "
                    "Win Probability"
                ),
                (
                    f"{result['current_home_win_probability']:.1%}"
                ),
            )

        with right:
            st.metric(
                "Game State",
                center_status,
            )

    else:
        winner = (
            home_team[
                "tricode"
            ]
            if home_score
            > away_score
            else away_team[
                "tricode"
            ]
        )

        with left:
            st.metric(
                "Last Live Win Probability",
                (
                    f"{result['current_home_win_probability']:.1%}"
                ),
            )

        with right:
            st.metric(
                "Winner",
                winner,
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

    st.plotly_chart(
        figure,
        use_container_width=True,
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
            "Swings"
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
            "Swings"
        )

        for _, row in (
            away_swings.iterrows()
        ):
            render_swing_card(
                row,
                away_team,
                "away",
            )


    with st.expander(
        "View prediction timeline"
    ):
        st.dataframe(
            game_df,
            use_container_width=True,
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