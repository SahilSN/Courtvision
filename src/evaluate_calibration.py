import os

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch

from sklearn.calibration import calibration_curve
from sklearn.metrics import (
    brier_score_loss,
    log_loss,
    roc_auc_score,
)

from feature_engineering import add_model_features
from model import WinProbabilityMLP


# -------------------------
# Configuration
# -------------------------

DATA_PATH = (
    "data/training/"
    "2024-25_training_v4_base.csv"
)

V4_MODEL_PATH = (
    "models/win_probability_mlp_v4.pt"
)

V4_SCALER_PATH = (
    "models/win_probability_scaler_v4.pkl"
)

V7_MODEL_PATH = (
    "models/win_probability_mlp_v7.pt"
)

V7_SCALER_PATH = (
    "models/win_probability_scaler_v7.pkl"
)

OUTPUT_DIR = "results"

OUTPUT_PATH = os.path.join(
    OUTPUT_DIR,
    "calibration_v4_vs_v7.png",
)

os.makedirs(
    OUTPUT_DIR,
    exist_ok=True,
)


# -------------------------
# Feature sets
# -------------------------

V4_FEATURES = [
    "elapsedGameTime",
    "homeScoreDiff",
    "homePossession",
    "totalScore",
    "homePreGameWinPct",
    "awayPreGameWinPct",
    "strengthDifference",
]

V7_FEATURES = [
    "elapsedGameTime",
    "homeScoreDiff",
    "homePossession",
    "totalScore",
    "homePreGameWinPct",
    "awayPreGameWinPct",
    "strengthDifference",
    "scoreDiffLateWeight",
]

TARGET = "homeWin"


# -------------------------
# Device
# -------------------------

device = torch.device(
    "mps"
    if torch.backends.mps.is_available()
    else "cpu"
)

print(
    "Using device:",
    device,
)


# -------------------------
# Load + engineer data
# -------------------------

df = pd.read_csv(
    DATA_PATH
)

df = add_model_features(
    df
)


# -------------------------
# Recreate chronological split
# -------------------------

game_table = (
    df[
        [
            "gameId",
            "gameDate",
        ]
    ]
    .drop_duplicates(
        subset="gameId"
    )
    .copy()
)

game_table["gameDate"] = pd.to_datetime(
    game_table["gameDate"]
)

game_table = (
    game_table
    .sort_values(
        [
            "gameDate",
            "gameId",
        ]
    )
    .reset_index(drop=True)
)

split_index = int(
    len(game_table) * 0.8
)

val_games = (
    game_table
    .iloc[split_index:]["gameId"]
    .to_numpy()
)

val_df = df[
    df["gameId"].isin(
        val_games
    )
].copy()

print(
    "Validation games:",
    val_df["gameId"].nunique(),
)

print(
    "Validation rows:",
    len(val_df),
)

# -------------------------
# Weighted metrics
# -------------------------

def weighted_brier_score(
    labels,
    probabilities,
    weights,
):
    squared_error = (
        probabilities - labels
    ) ** 2

    return np.average(
        squared_error,
        weights=weights,
    )


def weighted_log_loss(
    labels,
    probabilities,
    weights,
):
    epsilon = 1e-15

    probabilities = np.clip(
        probabilities,
        epsilon,
        1 - epsilon,
    )

    losses = -(
        labels
        * np.log(probabilities)
        + (
            1 - labels
        )
        * np.log(
            1 - probabilities
        )
    )

    return np.average(
        losses,
        weights=weights,
    )

def print_weighted_metrics(
    name,
    labels,
    probabilities,
    weights,
):
    logloss = weighted_log_loss(
        labels,
        probabilities,
        weights,
    )

    brier = weighted_brier_score(
        labels,
        probabilities,
        weights,
    )

    auc = roc_auc_score(
        labels,
        probabilities,
        sample_weight=weights,
    )

    print(
        f"\n{name} game-balanced metrics"
    )

    print(
        f"Log loss: {logloss:.4f}"
    )

    print(
        f"Brier: {brier:.4f}"
    )

    print(
        f"ROC AUC: {auc:.4f}"
    )

# -------------------------
# Prediction helper
# -------------------------

def get_predictions(
    val_df,
    feature_names,
    model_path,
    scaler_path,
):
    scaler = joblib.load(
        scaler_path
    )

    X = val_df[
        feature_names
    ]

    X_scaled = scaler.transform(
        X
    )

    X_tensor = torch.tensor(
        X_scaled,
        dtype=torch.float32,
    ).to(device)

    model = WinProbabilityMLP(
        input_size=len(feature_names)
    ).to(device)

    state_dict = torch.load(
        model_path,
        map_location=device,
    )

    model.load_state_dict(
        state_dict
    )

    model.eval()

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
# Generate predictions
# -------------------------

v4_probs = get_predictions(
    val_df,
    V4_FEATURES,
    V4_MODEL_PATH,
    V4_SCALER_PATH,
)

v7_probs = get_predictions(
    val_df,
    V7_FEATURES,
    V7_MODEL_PATH,
    V7_SCALER_PATH,
)

labels = (
    val_df[TARGET]
    .to_numpy()
)

# -------------------------
# Game-balanced weights
# -------------------------

rows_per_game = (
    val_df
    .groupby("gameId")["gameId"]
    .transform("count")
    .to_numpy()
)

game_weights = (
    1.0 / rows_per_game
)

# -------------------------
# Standard metrics
# -------------------------

def print_metrics(
    name,
    labels,
    probabilities,
):
    print(
        f"\n{name}"
    )

    print(
        "Log loss:",
        f"{log_loss(labels, probabilities):.4f}",
    )

    print(
        "Brier:",
        f"{brier_score_loss(labels, probabilities):.4f}",
    )

    print(
        "ROC AUC:",
        f"{roc_auc_score(labels, probabilities):.4f}",
    )


print_metrics(
    "V4",
    labels,
    v4_probs,
)

print_metrics(
    "V7",
    labels,
    v7_probs,
)


# -------------------------
# Calibration curves
# -------------------------

v4_true, v4_pred = calibration_curve(
    labels,
    v4_probs,
    n_bins=10,
    strategy="uniform",
)

v7_true, v7_pred = calibration_curve(
    labels,
    v7_probs,
    n_bins=10,
    strategy="uniform",
)


# -------------------------
# Print calibration table
# -------------------------

print(
    "\nV4 calibration"
)

for predicted, actual in zip(
    v4_pred,
    v4_true,
):
    print(
        f"Predicted: {predicted:.3f} | "
        f"Actual: {actual:.3f}"
    )


print(
    "\nV7 calibration"
)

for predicted, actual in zip(
    v7_pred,
    v7_true,
):
    print(
        f"Predicted: {predicted:.3f} | "
        f"Actual: {actual:.3f}"
    )


def expected_calibration_error(
    labels,
    probabilities,
    n_bins=10,
):
    bin_edges = np.linspace(
        0.0,
        1.0,
        n_bins + 1,
    )

    ece = 0.0

    for i in range(n_bins):

        lower = bin_edges[i]
        upper = bin_edges[i + 1]

        if i == n_bins - 1:
            mask = (
                (probabilities >= lower)
                & (probabilities <= upper)
            )
        else:
            mask = (
                (probabilities >= lower)
                & (probabilities < upper)
            )

        count = mask.sum()

        if count == 0:
            continue

        avg_confidence = (
            probabilities[mask].mean()
        )

        avg_accuracy = (
            labels[mask].mean()
        )

        bin_weight = (
            count
            / len(probabilities)
        )

        ece += (
            bin_weight
            * abs(
                avg_confidence
                - avg_accuracy
            )
        )

    return ece

def weighted_calibration_curve(
    labels,
    probabilities,
    weights,
    n_bins=10,
):
    bin_edges = np.linspace(
        0.0,
        1.0,
        n_bins + 1,
    )

    mean_predicted = []
    observed_frequency = []

    for i in range(n_bins):

        lower = bin_edges[i]
        upper = bin_edges[i + 1]

        if i == n_bins - 1:
            mask = (
                (probabilities >= lower)
                & (probabilities <= upper)
            )
        else:
            mask = (
                (probabilities >= lower)
                & (probabilities < upper)
            )

        if not mask.any():
            continue

        bin_weights = (
            weights[mask]
        )

        mean_predicted.append(
            np.average(
                probabilities[mask],
                weights=bin_weights,
            )
        )

        observed_frequency.append(
            np.average(
                labels[mask],
                weights=bin_weights,
            )
        )

    return (
        np.array(
            observed_frequency
        ),
        np.array(
            mean_predicted
        ),
    )

def weighted_expected_calibration_error(
    labels,
    probabilities,
    weights,
    n_bins=10,
):
    bin_edges = np.linspace(
        0.0,
        1.0,
        n_bins + 1,
    )

    total_weight = (
        weights.sum()
    )

    ece = 0.0

    for i in range(n_bins):

        lower = bin_edges[i]
        upper = bin_edges[i + 1]

        if i == n_bins - 1:
            mask = (
                (probabilities >= lower)
                & (probabilities <= upper)
            )
        else:
            mask = (
                (probabilities >= lower)
                & (probabilities < upper)
            )

        if not mask.any():
            continue

        bin_weights = (
            weights[mask]
        )

        bin_weight = (
            bin_weights.sum()
        )

        avg_confidence = np.average(
            probabilities[mask],
            weights=bin_weights,
        )

        avg_accuracy = np.average(
            labels[mask],
            weights=bin_weights,
        )

        ece += (
            bin_weight
            / total_weight
        ) * abs(
            avg_confidence
            - avg_accuracy
        )

    return ece

# -------------------------
# Plot
# -------------------------

fig, ax = plt.subplots(
    figsize=(8, 8)
)

ax.plot(
    [0, 1],
    [0, 1],
    linestyle="--",
    label="Perfect calibration",
)

ax.plot(
    v4_pred,
    v4_true,
    marker="o",
    label="V4",
)

ax.plot(
    v7_pred,
    v7_true,
    marker="o",
    label="V7",
)

ax.set_xlabel(
    "Predicted home win probability"
)

ax.set_ylabel(
    "Observed home win frequency"
)

ax.set_title(
    "Courtvision Win Probability Calibration"
)

ax.set_xlim(
    0,
    1,
)

ax.set_ylim(
    0,
    1,
)

ax.legend()

ax.grid(
    alpha=0.3
)

fig.tight_layout()

fig.savefig(
    OUTPUT_PATH,
    dpi=200,
)

print(
    "\nSaved calibration plot:",
    OUTPUT_PATH,
)

v4_ece = expected_calibration_error(
    labels,
    v4_probs,
)

v7_ece = expected_calibration_error(
    labels,
    v7_probs,
)

print(
    "\nExpected Calibration Error"
)

print(
    f"V4: {v4_ece:.4f}"
)

print(
    f"V7: {v7_ece:.4f}"
)

print_weighted_metrics(
    "V4",
    labels,
    v4_probs,
    game_weights,
)

print_weighted_metrics(
    "V7",
    labels,
    v7_probs,
    game_weights,
)

v4_weighted_ece = (
    weighted_expected_calibration_error(
        labels,
        v4_probs,
        game_weights,
    )
)

v7_weighted_ece = (
    weighted_expected_calibration_error(
        labels,
        v7_probs,
        game_weights,
    )
)

print(
    "\nGame-balanced ECE"
)

print(
    f"V4: {v4_weighted_ece:.4f}"
)

print(
    f"V7: {v7_weighted_ece:.4f}"
)

v4_balanced_true, v4_balanced_pred = (
    weighted_calibration_curve(
        labels,
        v4_probs,
        game_weights,
    )
)

v7_balanced_true, v7_balanced_pred = (
    weighted_calibration_curve(
        labels,
        v7_probs,
        game_weights,
    )
)

fig, ax = plt.subplots(
    figsize=(8, 8)
)

ax.plot(
    [0, 1],
    [0, 1],
    linestyle="--",
    label="Perfect calibration",
)

ax.plot(
    v4_balanced_pred,
    v4_balanced_true,
    marker="o",
    label="V4",
)

ax.plot(
    v7_balanced_pred,
    v7_balanced_true,
    marker="o",
    label="V7",
)

ax.set_xlabel(
    "Predicted home win probability"
)

ax.set_ylabel(
    "Observed home win frequency"
)

ax.set_title(
    "Courtvision Game-Balanced Calibration"
)

ax.set_xlim(
    0,
    1,
)

ax.set_ylim(
    0,
    1,
)

ax.legend()

ax.grid(
    alpha=0.3
)

fig.tight_layout()

balanced_output_path = os.path.join(
    OUTPUT_DIR,
    "calibration_v4_vs_v7_game_balanced.png",
)

fig.savefig(
    balanced_output_path,
    dpi=200,
)

print(
    "\nSaved game-balanced calibration plot:",
    balanced_output_path,
)

plt.show()