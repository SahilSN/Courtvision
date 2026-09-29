from pathlib import Path

import joblib
import pandas as pd
import torch

from nba_api.stats.endpoints import (
    playbyplayv3,
    teamgamelogs,
)

from feature_engineering import (
    MODEL_FEATURES,
    add_live_model_features,
    get_pregame_context,
)

from model import (
    WinProbabilityMLP,
)

from preprocess import (
    preprocess_live_game,
)


ROOT_DIR = (
    Path(__file__)
    .resolve()
    .parents[1]
)

MODEL_PATH = (
    ROOT_DIR
    / "models"
    / "win_probability_mlp_v7.pt"
)

SCALER_PATH = (
    ROOT_DIR
    / "models"
    / "win_probability_scaler_v7.pkl"
)


def load_live_artifacts():
    device = torch.device(
        "mps"
        if torch.backends.mps.is_available()
        else "cpu"
    )

    scaler = joblib.load(
        SCALER_PATH
    )

    model = WinProbabilityMLP(
        input_size=len(
            MODEL_FEATURES
        )
    ).to(device)

    state_dict = torch.load(
        MODEL_PATH,
        map_location=device,
    )

    model.load_state_dict(
        state_dict
    )

    model.eval()

    return (
        model,
        scaler,
        device,
    )


def normalize_game_id(
    game_id,
):
    return str(
        game_id
    ).zfill(10)


def fetch_live_play_by_play(
    game_id,
    timeout=60,
):
    canonical_game_id = (
        normalize_game_id(
            game_id
        )
    )

    pbp = (
        playbyplayv3
        .PlayByPlayV3(
            game_id=(
                canonical_game_id
            ),
            timeout=timeout,
        )
    )

    df = (
        pbp
        .get_data_frames()[0]
        .copy()
    )

    if df.empty:
        raise ValueError(
            "No PlayByPlayV3 data "
            f"returned for "
            f"{canonical_game_id}."
        )

    return df


def local_season_path(
    season,
):
    return (
        ROOT_DIR
        / "data"
        / "training"
        / (
            f"{season}"
            "_training_v4_base.csv"
        )
    )


def get_local_pregame_context(
    game_id,
    season,
):
    path = (
        local_season_path(
            season
        )
    )

    if not path.exists():
        return None

    season_df = pd.read_csv(
        path
    )

    numeric_game_id = int(
        str(game_id)
    )

    available_ids = set(
        season_df[
            "gameId"
        ]
        .astype(int)
        .unique()
    )

    if (
        numeric_game_id
        not in available_ids
    ):
        return None

    return get_pregame_context(
        season_df,
        numeric_game_id,
    )


def fetch_team_record_before_game(
    team_id,
    season,
    game_date,
    season_type="Regular Season",
    timeout=60,
):
    """
    Fetch only games completed before the
    selected game's calendar date.

    That reproduces V7's raw pregame W-L
    semantics without using future games.
    """

    selected_date = (
        pd.Timestamp(
            game_date
        )
        .normalize()
    )

    cutoff_date = (
        selected_date
        - pd.Timedelta(
            days=1
        )
    )

    cutoff_string = (
        cutoff_date.strftime(
            "%m/%d/%Y"
        )
    )

    endpoint = (
        teamgamelogs
        .TeamGameLogs(
            team_id_nullable=str(
                int(
                    team_id
                )
            ),
            season_nullable=season,
            season_type_nullable=(
                season_type
            ),
            date_to_nullable=(
                cutoff_string
            ),
            timeout=timeout,
        )
    )

    df = (
        endpoint
        .get_data_frames()[0]
        .copy()
    )

    if df.empty:
        return {
            "wins": 0,
            "losses": 0,
            "win_pct": 0.5,
        }

    wins = int(
        (
            df["WL"]
            == "W"
        ).sum()
    )

    losses = int(
        (
            df["WL"]
            == "L"
        ).sum()
    )

    games_played = (
        wins
        + losses
    )

    if games_played == 0:
        win_pct = 0.5

    else:
        win_pct = (
            wins
            / games_played
        )

    return {
        "wins":
            wins,

        "losses":
            losses,

        "win_pct":
            win_pct,
    }


def build_pregame_context(
    game_id,
    home_team_id,
    away_team_id,
    season,
    game_date,
    season_type="Regular Season",
):
    local_context = (
        get_local_pregame_context(
            game_id,
            season,
        )
    )

    if (
        local_context
        is not None
    ):
        return local_context

    home_record = (
        fetch_team_record_before_game(
            team_id=(
                home_team_id
            ),
            season=season,
            game_date=(
                game_date
            ),
            season_type=(
                season_type
            ),
        )
    )

    away_record = (
        fetch_team_record_before_game(
            team_id=(
                away_team_id
            ),
            season=season,
            game_date=(
                game_date
            ),
            season_type=(
                season_type
            ),
        )
    )

    home_pct = (
        home_record[
            "win_pct"
        ]
    )

    away_pct = (
        away_record[
            "win_pct"
        ]
    )

    return {
        "homeTeamId":
            int(
                home_team_id
            ),

        "awayTeamId":
            int(
                away_team_id
            ),

        "homePreGameWins":
            home_record[
                "wins"
            ],

        "homePreGameLosses":
            home_record[
                "losses"
            ],

        "awayPreGameWins":
            away_record[
                "wins"
            ],

        "awayPreGameLosses":
            away_record[
                "losses"
            ],

        "homePreGameWinPct":
            home_pct,

        "awayPreGameWinPct":
            away_pct,

        "strengthDifference":
            (
                home_pct
                - away_pct
            ),
    }


def predict_live_probabilities(
    game_df,
    model,
    scaler,
    device,
):
    X = game_df[
        MODEL_FEATURES
    ]

    X_scaled = (
        scaler.transform(
            X
        )
    )

    X_tensor = (
        torch.tensor(
            X_scaled,
            dtype=torch.float32,
        )
        .to(device)
    )

    with torch.no_grad():
        logits = model(
            X_tensor
        )

        probabilities = (
            torch.sigmoid(
                logits
            )
            .cpu()
            .numpy()
            .flatten()
        )

    result_df = (
        game_df.copy()
    )

    result_df[
        "winProbability"
    ] = probabilities

    return result_df


def find_live_turning_points(
    game_df,
    top_k=3,
):
    df = (
        game_df.copy()
    )

    df[
        "previousWinProbability"
    ] = (
        df[
            "winProbability"
        ]
        .shift(1)
    )

    df[
        "probabilityChange"
    ] = (
        df[
            "winProbability"
        ]
        .diff()
    )

    valid = (
        df
        .dropna(
            subset=[
                "probabilityChange"
            ]
        )
        .copy()
    )

    home_swings = (
        valid
        .nlargest(
            top_k,
            "probabilityChange",
        )
        .copy()
    )

    away_swings = (
        valid
        .nsmallest(
            top_k,
            "probabilityChange",
        )
        .copy()
    )

    return (
        home_swings,
        away_swings,
    )


def get_game_state(
    game_df,
):
    row = (
        game_df.iloc[-1]
    )

    return {
        "period":
            int(
                row[
                    "period"
                ]
            ),

        "clock":
            row[
                "clock"
            ],

        "score_home":
            int(
                row[
                    "scoreHome"
                ]
            ),

        "score_away":
            int(
                row[
                    "scoreAway"
                ]
            ),
    }


def format_api_clock(
    clock,
):
    if clock is None:
        return ""

    clock_text = str(
        clock
    )

    if (
        clock_text.startswith(
            "PT"
        )
        and "M" in clock_text
        and "S" in clock_text
    ):
        try:
            time_part = (
                clock_text[2:]
            )

            (
                minutes_text,
                seconds_text,
            ) = (
                time_part.split(
                    "M",
                    1,
                )
            )

            seconds_text = (
                seconds_text
                .replace(
                    "S",
                    "",
                )
            )

            minutes = int(
                minutes_text
                or 0
            )

            seconds = int(
                float(
                    seconds_text
                )
            )

            return (
                f"{minutes}:"
                f"{seconds:02d}"
            )

        except (
            ValueError,
            TypeError,
        ):
            pass

    return clock_text


def format_live_status(
    period,
    clock,
):
    clock_text = (
        format_api_clock(
            clock
        )
    )

    if period <= 0:
        return "Scheduled"

    if period <= 4:
        return (
            f"Q{period} · "
            f"{clock_text}"
        )

    return (
        f"OT{period - 4} · "
        f"{clock_text}"
    )


def add_terminal_state(
    game_df,
):
    df = (
        game_df.copy()
    )

    df[
        "isTerminalState"
    ] = False

    last_row = (
        df.iloc[-1]
        .copy()
    )

    final_probability = float(
        last_row[
            "scoreHome"
        ]
        >
        last_row[
            "scoreAway"
        ]
    )

    terminal = (
        last_row.copy()
    )

    terminal[
        "elapsedGameTime"
    ] = (
        float(
            last_row[
                "elapsedGameTime"
            ]
        )
        + 1.0
    )

    terminal[
        "winProbability"
    ] = (
        final_probability
    )

    terminal[
        "isTerminalState"
    ] = True

    return pd.concat(
        [
            df,
            terminal
            .to_frame()
            .T,
        ],
        ignore_index=True,
    )


def analyze_live_game(
    game_id,
    season,
    game_date,
    season_type="Regular Season",
    top_k=3,
    assume_final=False,
):
    canonical_game_id = (
        normalize_game_id(
            game_id
        )
    )

    raw_df = (
        fetch_live_play_by_play(
            canonical_game_id
        )
    )

    game_df = (
        preprocess_live_game(
            raw_df
        )
    )

    if game_df.empty:
        raise ValueError(
            "No usable states "
            "after preprocessing."
        )

    home_team_id = int(
        game_df[
            "homeTeamId"
        ].iloc[0]
    )

    away_team_id = int(
        game_df[
            "awayTeamId"
        ].iloc[0]
    )

    context = (
        build_pregame_context(
            game_id=(
                canonical_game_id
            ),
            home_team_id=(
                home_team_id
            ),
            away_team_id=(
                away_team_id
            ),
            season=season,
            game_date=(
                game_date
            ),
            season_type=(
                season_type
            ),
        )
    )

    game_df = (
        add_live_model_features(
            game_df,
            context,
        )
    )

    (
        model,
        scaler,
        device,
    ) = load_live_artifacts()

    game_df = (
        predict_live_probabilities(
            game_df,
            model,
            scaler,
            device,
        )
    )

    (
        home_swings,
        away_swings,
    ) = (
        find_live_turning_points(
            game_df,
            top_k=top_k,
        )
    )

    model_timeline = (
        game_df.copy()
    )

    state = (
        get_game_state(
            game_df
        )
    )

    current_probability = float(
        game_df[
            "winProbability"
        ].iloc[-1]
    )

    if assume_final:
        timeline = (
            add_terminal_state(
                game_df
            )
        )

        display_status = (
            "FINAL"
        )

        status = (
            "final"
        )

    else:
        timeline = (
            game_df.copy()
        )

        display_status = (
            format_live_status(
                state[
                    "period"
                ],
                state[
                    "clock"
                ],
            )
        )

        status = (
            "live_mode"
        )

    result = {
        "game_id":
            canonical_game_id,

        "game_date":
            str(
                game_date
            ),

        "home_team_id":
            home_team_id,

        "away_team_id":
            away_team_id,

        "home_pre_game_wins":
            int(
                context[
                    "homePreGameWins"
                ]
            ),

        "home_pre_game_losses":
            int(
                context[
                    "homePreGameLosses"
                ]
            ),

        "away_pre_game_wins":
            int(
                context[
                    "awayPreGameWins"
                ]
            ),

        "away_pre_game_losses":
            int(
                context[
                    "awayPreGameLosses"
                ]
            ),

        "home_pre_game_win_pct":
            float(
                context[
                    "homePreGameWinPct"
                ]
            ),

        "away_pre_game_win_pct":
            float(
                context[
                    "awayPreGameWinPct"
                ]
            ),

        "strength_difference":
            float(
                context[
                    "strengthDifference"
                ]
            ),

        "current_home_win_probability":
            current_probability,

        "current_home_score":
            state[
                "score_home"
            ],

        "current_away_score":
            state[
                "score_away"
            ],

        "period":
            state[
                "period"
            ],

        "clock":
            state[
                "clock"
            ],

        "display_status":
            display_status,

        "timeline":
            timeline,

        "model_timeline":
            model_timeline,

        "home_swings":
            home_swings,

        "away_swings":
            away_swings,

        "status":
            status,

        "is_final":
            assume_final,
    }

    if assume_final:
        result[
            "final_home_score"
        ] = state[
            "score_home"
        ]

        result[
            "final_away_score"
        ] = state[
            "score_away"
        ]

        result[
            "final_home_win_probability"
        ] = float(
            state[
                "score_home"
            ]
            >
            state[
                "score_away"
            ]
        )

    return result