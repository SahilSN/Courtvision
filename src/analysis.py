import joblib
import pandas as pd
import torch

from feature_engineering import (
    add_model_features,
    MODEL_FEATURES,
)
from model import WinProbabilityMLP


# -------------------------
# Configuration
# -------------------------

DATA_PATH = (
    "data/training/"
    "2024-25_training_v4_base.csv"
)

MODEL_PATH = (
    "models/"
    "win_probability_mlp_v7.pt"
)

SCALER_PATH = (
    "models/"
    "win_probability_scaler_v7.pkl"
)


# -------------------------
# Game ID helpers
# -------------------------

def normalize_training_game_id(
    game_id,
):
    """
    Convert either:

        22401197

    or:

        0022401197

    into the integer representation used
    by the training CSV:

        22401197
    """

    return int(
        str(game_id)
    )


def normalize_display_game_id(
    game_id,
):
    """
    Convert a game ID into the canonical
    10-digit NBA representation.
    """

    return str(
        game_id
    ).zfill(10)


# -------------------------
# Load trained artifacts
# -------------------------

def load_artifacts():
    device = torch.device(
        "mps"
        if torch.backends.mps.is_available()
        else "cpu"
    )

    scaler = joblib.load(
        SCALER_PATH
    )

    model = WinProbabilityMLP(
        input_size=len(MODEL_FEATURES)
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


# -------------------------
# Prepare one game
# -------------------------

def prepare_game(
    df,
    game_id,
    scaler,
):
    training_game_id = (
        normalize_training_game_id(
            game_id
        )
    )

    game_df = df[
        df["gameId"]
        == training_game_id
    ].copy()

    if game_df.empty:
        raise ValueError(
            f"Game {game_id} not found."
        )

    game_df = (
        game_df
        .sort_values(
            "elapsedGameTime",
            kind="mergesort",
        )
        .reset_index(drop=True)
    )

    X = game_df[
        MODEL_FEATURES
    ]

    X_scaled = scaler.transform(
        X
    )

    X_tensor = torch.tensor(
        X_scaled,
        dtype=torch.float32,
    )

    return (
        game_df,
        X_tensor,
    )


# -------------------------
# Run MLP inference
# -------------------------

def predict_probabilities(
    model,
    X_tensor,
    device,
):
    X_tensor = X_tensor.to(
        device
    )

    with torch.no_grad():
        logits = model(
            X_tensor
        )

        probabilities = torch.sigmoid(
            logits
        )

    return (
        probabilities
        .cpu()
        .numpy()
        .flatten()
    )


# -------------------------
# Find largest probability swings
# -------------------------

def find_turning_points(
    game_df,
    top_k=3,
):
    game_df = game_df.copy()

    game_df[
        "previousWinProbability"
    ] = (
        game_df[
            "winProbability"
        ]
        .shift(1)
    )

    game_df[
        "probabilityChange"
    ] = (
        game_df[
            "winProbability"
        ]
        .diff()
    )

    columns = [
        "elapsedGameTime",
        "period",
        "clock",
        "teamTricode",
        "actionType",
        "description",
        "previousWinProbability",
        "winProbability",
        "probabilityChange",
    ]

    home_swings = (
        game_df
        .nlargest(
            top_k,
            "probabilityChange",
        )[columns]
        .copy()
    )

    away_swings = (
        game_df
        .nsmallest(
            top_k,
            "probabilityChange",
        )[columns]
        .copy()
    )

    return (
        home_swings,
        away_swings,
    )


# -------------------------
# Create terminal display state
# -------------------------

def add_terminal_state(
    game_df,
):
    """
    Historical games are completed games.

    The neural network's final state may still
    predict something like 92.7%, because the
    model itself does not contain a hard rule
    saying that a completed game must be 0%/100%.

    Keep the final model prediction untouched,
    then append a display-only terminal point
    corresponding to the known game result.
    """

    if game_df.empty:
        raise ValueError(
            "Cannot add terminal state "
            "to an empty game."
        )

    display_df = game_df.copy()

    home_win = int(
        game_df[
            "homeWin"
        ].iloc[-1]
    )

    final_probability = float(
        home_win
    )

    last_time = float(
        game_df[
            "elapsedGameTime"
        ].iloc[-1]
    )

    # Regulation ends at 2880 seconds.
    #
    # For overtime games, preserve the
    # later elapsed time instead.
    terminal_time = max(
        2880.0,
        last_time,
    )

    terminal_row = (
        game_df
        .iloc[-1]
        .copy()
    )

    terminal_row[
        "elapsedGameTime"
    ] = terminal_time

    terminal_row[
        "winProbability"
    ] = final_probability

    # These fields make it clear to future
    # consumers that this row is not another
    # neural-network prediction.
    terminal_row[
        "isTerminalState"
    ] = True

    display_df[
        "isTerminalState"
    ] = False

    display_df = pd.concat(
        [
            display_df,
            terminal_row
            .to_frame()
            .T,
        ],
        ignore_index=True,
    )

    return (
        display_df,
        final_probability,
    )


# -------------------------
# Main reusable analysis API
# -------------------------

def analyze_game(
    game_id,
    add_play_by_play_details_fn=None,
    top_k=3,
):
    """
    Analyze a completed historical NBA game.

    Returns structured Courtvision results that
    can be consumed by either the CLI plotting
    script or a future dashboard.
    """

    # -------------------------
    # Load V7 artifacts
    # -------------------------

    model, scaler, device = (
        load_artifacts()
    )

    # -------------------------
    # Load entire season
    # -------------------------
    #
    # This MUST happen before selecting the
    # requested game because V7's pregame
    # strength features depend on all games
    # played earlier in the season.

    df = pd.read_csv(
        DATA_PATH
    )

    df = add_model_features(
        df
    )

    # -------------------------
    # Select requested game
    # -------------------------

    game_df, X_tensor = (
        prepare_game(
            df,
            game_id,
            scaler,
        )
    )

    # -------------------------
    # Generate V7 probabilities
    # -------------------------

    probabilities = (
        predict_probabilities(
            model,
            X_tensor,
            device,
        )
    )

    game_df[
        "winProbability"
    ] = probabilities

    # -------------------------
    # Attach original PBP metadata
    # -------------------------

    if (
        add_play_by_play_details_fn
        is not None
    ):
        game_df = (
            add_play_by_play_details_fn(
                game_df,
                game_id,
            )
        )

    # -------------------------
    # Turning points
    # -------------------------
    #
    # IMPORTANT:
    # Calculate these BEFORE adding the
    # artificial terminal 0%/100% point.
    #
    # Otherwise the end-of-game jump itself
    # could incorrectly become the biggest
    # "turning point."

    home_swings, away_swings = (
        find_turning_points(
            game_df,
            top_k=top_k,
        )
    )

    # -------------------------
    # Final model estimate
    # -------------------------

    current_probability = float(
        game_df[
            "winProbability"
        ].iloc[-1]
    )

    # -------------------------
    # Known final outcome
    # -------------------------

    (
        display_timeline,
        final_probability,
    ) = add_terminal_state(
        game_df
    )

    # -------------------------
    # Final score
    # -------------------------
    #
    # Scores are cumulative, so max() is a
    # little more robust than relying on the
    # exact final retained possession row.

    final_home_score = int(
        game_df[
            "scoreHome"
        ].max()
    )

    final_away_score = int(
        game_df[
            "scoreAway"
        ].max()
    )

    # -------------------------
    # Game metadata
    # -------------------------

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

    game_date = str(
        game_df[
            "gameDate"
        ].iloc[0]
    )

    # Pregame strength is constant
    # throughout the game.

    home_pre_game_win_pct = float(
        game_df[
            "homePreGameWinPct"
        ].iloc[0]
    )

    away_pre_game_win_pct = float(
        game_df[
            "awayPreGameWinPct"
        ].iloc[0]
    )

    home_pre_game_wins = int(
        game_df[
            "homePreGameWins"
        ].iloc[0]
    )

    home_pre_game_losses = int(
        game_df[
            "homePreGameLosses"
        ].iloc[0]
    )

    away_pre_game_wins = int(
        game_df[
            "awayPreGameWins"
        ].iloc[0]
    )

    away_pre_game_losses = int(
        game_df[
            "awayPreGameLosses"
        ].iloc[0]
    )

    strength_difference = float(
        game_df[
            "strengthDifference"
        ].iloc[0]
    )

    # -------------------------
    # Structured result
    # -------------------------

    result = {
        "game_id":
            normalize_display_game_id(
                game_id
            ),

        "training_game_id":
            normalize_training_game_id(
                game_id
            ),

        "game_date":
            game_date,

        "home_team_id":
            home_team_id,

        "away_team_id":
            away_team_id,

        "final_home_score":
            final_home_score,

        "final_away_score":
            final_away_score,

        # Final neural-network estimate before
        # forcing the known completed result.
        "current_home_win_probability":
            current_probability,

        # Known completed-game outcome.
        "final_home_win_probability":
            final_probability,

        "home_pre_game_win_pct":
            home_pre_game_win_pct,

        "away_pre_game_win_pct":
            away_pre_game_win_pct,

        "home_pre_game_wins":
            home_pre_game_wins,

        "home_pre_game_losses":
            home_pre_game_losses,

        "away_pre_game_wins":
            away_pre_game_wins,

        "away_pre_game_losses":
            away_pre_game_losses,

        "strength_difference":
            strength_difference,

        # Actual neural-network predictions only.
        "model_timeline":
            game_df,

        # Same timeline with a display-only
        # terminal 0% or 100% point appended.
        "timeline":
            display_timeline,

        "home_swings":
            home_swings,

        "away_swings":
            away_swings,

        "is_final":
            True,
    }

    return result