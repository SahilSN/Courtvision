import joblib
import pandas as pd
import torch
from predict_game import add_play_by_play_details
from nba_api.stats.endpoints import (
    playbyplayv3,
)

from analysis import analyze_game
from feature_engineering import (
    MODEL_FEATURES,
    add_live_model_features,
    get_pregame_context,
)
from model import WinProbabilityMLP
from preprocess import (
    preprocess_live_game,
)


# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

GAME_ID = "0022400500"

TRAINING_GAME_ID = int(
    GAME_ID
)

SEASON_DATA_PATH = (
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


# ------------------------------------------------------------
# Fake-live cutoffs
# ------------------------------------------------------------
#
# elapsedGameTime is seconds since tipoff.
#
# Q1 end      = 720
# halftime    = 1440
# Q3 end      = 2160
# 5:00 Q4     = 2580
# 2:00 Q4     = 2760

CUTOFFS = [
    (
        "End Q1",
        720,
    ),
    (
        "Halftime",
        1440,
    ),
    (
        "End Q3",
        2160,
    ),
    (
        "5:00 Q4",
        2580,
    ),
    (
        "2:00 Q4",
        2760,
    ),
]


# ------------------------------------------------------------
# Load V7
# ------------------------------------------------------------

def load_model():
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


# ------------------------------------------------------------
# Predict final state in partial dataframe
# ------------------------------------------------------------

def predict_last_state(
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

    X_tensor = torch.tensor(
        X_scaled,
        dtype=torch.float32,
    ).to(device)

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

    return float(
        probabilities[-1]
    )


# ------------------------------------------------------------
# Find corresponding historical probability
# ------------------------------------------------------------

def get_historical_probability(
    historical_df,
    cutoff_time,
):
    eligible = historical_df[
        historical_df[
            "elapsedGameTime"
        ]
        <= cutoff_time
    ]

    if eligible.empty:
        return None

    return float(
        eligible[
            "winProbability"
        ].iloc[-1]
    )


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main():
    print(
        f"Fetching {GAME_ID} "
        "with PlayByPlayV3..."
    )

    pbp = playbyplayv3.PlayByPlayV3(
        game_id=GAME_ID,
        timeout=60,
    )

    raw_df = (
        pbp
        .get_data_frames()[0]
    )

    print(
        "Raw actions:",
        len(raw_df),
    )

    # --------------------------------------------------------
    # Process as though game were live.
    # --------------------------------------------------------

    live_df = (
        preprocess_live_game(
            raw_df
        )
    )

    print(
        "Live-compatible states:",
        len(live_df),
    )

    # --------------------------------------------------------
    # Get leakage-safe pregame team context from season data.
    # --------------------------------------------------------

    season_df = pd.read_csv(
        SEASON_DATA_PATH
    )

    pregame_context = (
        get_pregame_context(
            season_df,
            TRAINING_GAME_ID,
        )
    )

    print(
        "\nPregame context:"
    )

    for (
        key,
        value,
    ) in pregame_context.items():
        print(
            f"  {key}: {value}"
        )

    # --------------------------------------------------------
    # Add the exact V7 live features.
    # --------------------------------------------------------

    live_df = (
        add_live_model_features(
            live_df,
            pregame_context,
        )
    )

    # --------------------------------------------------------
    # Load trained V7.
    # --------------------------------------------------------

    (
        model,
        scaler,
        device,
    ) = load_model()

    # --------------------------------------------------------
    # Existing historical Courtvision analysis.
    # --------------------------------------------------------

    historical_result = (
        analyze_game(
            game_id=TRAINING_GAME_ID,
            add_play_by_play_details_fn=(
                add_play_by_play_details
            ),
            top_k=3,
        )
    )

    historical_df = (
        historical_result[
            "model_timeline"
        ]
    )

    # --------------------------------------------------------
    # Compare cutoff probabilities.
    # --------------------------------------------------------

    results = []

    print(
        "\nFake-live comparison"
    )

    print(
        "-" * 72
    )

    for (
        label,
        cutoff_time,
    ) in CUTOFFS:
        partial_df = live_df[
            live_df[
                "elapsedGameTime"
            ]
            <= cutoff_time
        ].copy()

        if partial_df.empty:
            print(
                f"{label}: "
                "no eligible rows"
            )

            continue

        live_probability = (
            predict_last_state(
                partial_df,
                model,
                scaler,
                device,
            )
        )

        actual_time = float(
            partial_df[
                "elapsedGameTime"
            ].iloc[-1]
        )

        historical_probability = (
            get_historical_probability(
                historical_df,
                actual_time,
            )
        )

        if historical_probability is None:
            difference = None
        else:
            difference = (
                live_probability
                - historical_probability
            )

        results.append(
            {
                "label":
                    label,

                "requestedCutoff":
                    cutoff_time,

                "actualStateTime":
                    actual_time,

                "fakeLiveProbability":
                    live_probability,

                "historicalProbability":
                    historical_probability,

                "difference":
                    difference,
            }
        )

        print(
            f"{label:10s} | "
            f"time={actual_time:7.1f} | "
            f"live={live_probability:7.3%} | "
            f"historical="
            f"{historical_probability:7.3%} | "
            f"diff="
            f"{difference:+.6f}"
        )

    # --------------------------------------------------------
    # Full game comparison
    # --------------------------------------------------------

    full_live_probability = (
        predict_last_state(
            live_df,
            model,
            scaler,
            device,
        )
    )

    full_historical_probability = (
        float(
            historical_df[
                "winProbability"
            ].iloc[-1]
        )
    )

    full_difference = (
        full_live_probability
        - full_historical_probability
    )

    print(
        "\nFull game"
    )

    print(
        f"Fake-live final model estimate: "
        f"{full_live_probability:.3%}"
    )

    print(
        f"Historical model estimate:      "
        f"{full_historical_probability:.3%}"
    )

    print(
        f"Difference:                     "
        f"{full_difference:+.8f}"
    )

    # --------------------------------------------------------
    # Save comparison
    # --------------------------------------------------------

    results.append(
        {
            "label":
                "Full game",

            "requestedCutoff":
                live_df[
                    "elapsedGameTime"
                ].iloc[-1],

            "actualStateTime":
                live_df[
                    "elapsedGameTime"
                ].iloc[-1],

            "fakeLiveProbability":
                full_live_probability,

            "historicalProbability":
                full_historical_probability,

            "difference":
                full_difference,
        }
    )

    results_df = pd.DataFrame(
        results
    )

    output_path = (
        "results/"
        "fake_live_validation.csv"
    )

    from pathlib import Path

    Path(
        "results"
    ).mkdir(
        exist_ok=True
    )

    results_df.to_csv(
        output_path,
        index=False,
    )

    print(
        "\nSaved:",
        output_path,
    )


if __name__ == "__main__":
    main()