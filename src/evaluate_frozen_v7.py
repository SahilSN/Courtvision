import argparse
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch

from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)

from feature_engineering import (
    MODEL_FEATURES,
    add_model_features,
)

from model import (
    WinProbabilityMLP,
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

RESULTS_DIR = (
    ROOT_DIR
    / "results"
)

N_BINS = 10


def expected_calibration_error(
    labels,
    probabilities,
    weights=None,
    n_bins=10,
):
    labels = np.asarray(
        labels,
        dtype=float,
    )

    probabilities = np.asarray(
        probabilities,
        dtype=float,
    )

    if weights is None:
        weights = np.ones(
            len(labels),
            dtype=float,
        )

    weights = np.asarray(
        weights,
        dtype=float,
    )

    edges = np.linspace(
        0.0,
        1.0,
        n_bins + 1,
    )

    total_weight = (
        weights.sum()
    )

    ece = 0.0

    for index in range(
        n_bins
    ):
        lower = edges[
            index
        ]

        upper = edges[
            index + 1
        ]

        if (
            index
            == n_bins - 1
        ):
            mask = (
                (
                    probabilities
                    >= lower
                )
                &
                (
                    probabilities
                    <= upper
                )
            )

        else:
            mask = (
                (
                    probabilities
                    >= lower
                )
                &
                (
                    probabilities
                    < upper
                )
            )

        if not mask.any():
            continue

        bin_weights = (
            weights[
                mask
            ]
        )

        predicted = np.average(
            probabilities[
                mask
            ],
            weights=(
                bin_weights
            ),
        )

        observed = np.average(
            labels[
                mask
            ],
            weights=(
                bin_weights
            ),
        )

        ece += (
            (
                bin_weights.sum()
                / total_weight
            )
            *
            abs(
                predicted
                - observed
            )
        )

    return float(
        ece
    )


def calculate_metrics(
    labels,
    probabilities,
    weights=None,
):
    predictions = (
        probabilities
        >= 0.5
    ).astype(int)

    if weights is None:
        accuracy = (
            accuracy_score(
                labels,
                predictions,
            )
        )

    else:
        accuracy = (
            np.average(
                predictions
                == labels,
                weights=weights,
            )
        )

    return {
        "accuracy":
            float(
                accuracy
            ),

        "log_loss":
            float(
                log_loss(
                    labels,
                    probabilities,
                    sample_weight=(
                        weights
                    ),
                )
            ),

        "brier":
            float(
                brier_score_loss(
                    labels,
                    probabilities,
                    sample_weight=(
                        weights
                    ),
                )
            ),

        "auc":
            float(
                roc_auc_score(
                    labels,
                    probabilities,
                    sample_weight=(
                        weights
                    ),
                )
            ),

        "ece":
            expected_calibration_error(
                labels,
                probabilities,
                weights=weights,
                n_bins=N_BINS,
            ),
    }


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


def predict(
    df,
):
    (
        model,
        scaler,
        device,
    ) = load_model()

    X = df[
        MODEL_FEATURES
    ]

    X_scaled = (
        scaler.transform(
            X
        )
    )

    tensor = (
        torch.tensor(
            X_scaled,
            dtype=torch.float32,
        )
        .to(device)
    )

    with torch.no_grad():
        probabilities = (
            torch.sigmoid(
                model(
                    tensor
                )
            )
            .cpu()
            .numpy()
            .flatten()
        )

    return (
        probabilities,
        device,
    )


def main():
    parser = (
        argparse.ArgumentParser()
    )

    parser.add_argument(
        "--season",
        default="2025-26",
    )

    args = (
        parser.parse_args()
    )

    data_path = (
        ROOT_DIR
        / "data"
        / "training"
        / (
            f"{args.season}"
            "_training_v4_base.csv"
        )
    )

    if not data_path.exists():
        raise FileNotFoundError(
            f"Missing {data_path}"
        )

    df = pd.read_csv(
        data_path
    )

    print(
        "Season:",
        args.season,
    )

    print(
        "Games:",
        df[
            "gameId"
        ].nunique(),
    )

    print(
        "Base rows:",
        len(
            df
        ),
    )

    df = (
        add_model_features(
            df
        )
    )

    probabilities, device = (
        predict(
            df
        )
    )

    labels = (
        df[
            "homeWin"
        ]
        .astype(int)
        .to_numpy()
    )

    rows_per_game = (
        df.groupby(
            "gameId"
        )[
            "gameId"
        ]
        .transform(
            "count"
        )
        .to_numpy()
    )

    game_weights = (
        1.0
        / rows_per_game
    )

    state_metrics = (
        calculate_metrics(
            labels,
            probabilities,
        )
    )

    game_metrics = (
        calculate_metrics(
            labels,
            probabilities,
            weights=(
                game_weights
            ),
        )
    )

    print(
        "Device:",
        device,
    )

    print()
    print(
        "Frozen V7 "
        "temporal evaluation"
    )

    print()
    print(
        "State-weighted"
    )

    for name, value in (
        state_metrics.items()
    ):
        print(
            f"{name:12s}: "
            f"{value:.4f}"
        )

    print()
    print(
        "Game-balanced"
    )

    for name, value in (
        game_metrics.items()
    ):
        print(
            f"{name:12s}: "
            f"{value:.4f}"
        )

    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    metrics_df = (
        pd.DataFrame(
            [
                {
                    "season":
                        args.season,

                    "weighting":
                        "state",

                    **state_metrics,
                },

                {
                    "season":
                        args.season,

                    "weighting":
                        "game_balanced",

                    **game_metrics,
                },
            ]
        )
    )

    metrics_path = (
        RESULTS_DIR
        / (
            f"v7_{args.season}"
            "_temporal_metrics.csv"
        )
    )

    metrics_df.to_csv(
        metrics_path,
        index=False,
    )

    prediction_df = (
        df[
            [
                "gameId",
                "gameDate",
                "elapsedGameTime",
                "homeWin",
            ]
        ]
        .copy()
    )

    prediction_df[
        "winProbability"
    ] = probabilities

    predictions_path = (
        RESULTS_DIR
        / (
            f"v7_{args.season}"
            "_predictions.csv"
        )
    )

    prediction_df.to_csv(
        predictions_path,
        index=False,
    )

    print()
    print(
        "Saved:",
        metrics_path,
    )

    print(
        "Saved:",
        predictions_path,
    )


if __name__ == "__main__":
    main()