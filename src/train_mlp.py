import os

import joblib
import pandas as pd
import torch

from torch import nn
from torch.utils.data import TensorDataset, DataLoader
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    accuracy_score,
    log_loss,
    brier_score_loss,
    roc_auc_score,
)

from feature_engineering import (
    add_model_features,
    MODEL_FEATURES,
)

from model import WinProbabilityMLP


# -------------------------
# Configuration
# -------------------------

FEATURES = [
    "elapsedGameTime",
    "homeScoreDiff",
    "homePossession",
]

TARGET = "homeWin"

TARGET = "homeWin"

MODEL_DIR = "models"

DATA_PATH = (
    "data/training/"
    "2024-25_training_v4_base.csv"
)

MODEL_PATH = os.path.join(
    MODEL_DIR,
    "win_probability_mlp_v7.pt",
)

SCALER_PATH = os.path.join(
    MODEL_DIR,
    "win_probability_scaler_v7.pkl",
)

BATCH_SIZE = 64
LEARNING_RATE = 0.001

EPOCHS = 25
PATIENCE = 5


# -------------------------
# Create model directory
# -------------------------

os.makedirs(
    MODEL_DIR,
    exist_ok=True,
)


# -------------------------
# Load data
# -------------------------

df = pd.read_csv(DATA_PATH)
df = add_model_features(df)

print(
    df[
        [
            "elapsedGameTime",
            "homeScoreDiff",
            "scoreDiffLateWeight",
        ]
    ]
    .head(30)
)

print(
    df[
        [
            "elapsedGameTime",
            "homeScoreDiff",
            "scoreDiffLateWeight",
        ]
    ]
    .sort_values(
        "elapsedGameTime"
    )
    .tail(20)
)

print(
    df[MODEL_FEATURES]
    .isna()
    .sum()
)


# -------------------------
# Train / validation split
# -------------------------

game_ids = df["gameId"].unique()

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

train_games = (
    game_table
    .iloc[:split_index]["gameId"]
    .to_numpy()
)

val_games = (
    game_table
    .iloc[split_index:]["gameId"]
    .to_numpy()
)

train_df = df[
    df["gameId"].isin(train_games)
].copy()

val_df = df[
    df["gameId"].isin(val_games)
].copy()

train_df = df[
    df["gameId"].isin(train_games)
].copy()

val_df = df[
    df["gameId"].isin(val_games)
].copy()

print(
    "Train games:",
    train_df["gameId"].nunique(),
)

print(
    "Validation games:",
    val_df["gameId"].nunique(),
)

print(
    "Train rows:",
    len(train_df),
)

print(
    "Validation rows:",
    len(val_df),
)


# -------------------------
# Separate features / labels
# -------------------------

X_train = train_df[MODEL_FEATURES]
X_val = val_df[MODEL_FEATURES]

print(df[MODEL_FEATURES].head())
print(df[MODEL_FEATURES].isna().sum())

y_train = train_df[TARGET]
y_val = val_df[TARGET]


# -------------------------
# Scale features
# -------------------------

scaler = StandardScaler()

X_train_scaled = scaler.fit_transform(
    X_train
)

X_val_scaled = scaler.transform(
    X_val
)

joblib.dump(
    scaler,
    SCALER_PATH,
)

print(
    "Saved scaler to:",
    SCALER_PATH,
)


# -------------------------
# Convert to tensors
# -------------------------

X_train_tensor = torch.tensor(
    X_train_scaled,
    dtype=torch.float32,
)

X_val_tensor = torch.tensor(
    X_val_scaled,
    dtype=torch.float32,
)

y_train_tensor = torch.tensor(
    y_train.to_numpy(),
    dtype=torch.float32,
).unsqueeze(1)

y_val_tensor = torch.tensor(
    y_val.to_numpy(),
    dtype=torch.float32,
).unsqueeze(1)

print(
    "X_train:",
    X_train_tensor.shape,
)

print(
    "y_train:",
    y_train_tensor.shape,
)

print(
    "X_val:",
    X_val_tensor.shape,
)

print(
    "y_val:",
    y_val_tensor.shape,
)


# -------------------------
# Create datasets
# -------------------------

train_dataset = TensorDataset(
    X_train_tensor,
    y_train_tensor,
)

val_dataset = TensorDataset(
    X_val_tensor,
    y_val_tensor,
)


# -------------------------
# Create data loaders
# -------------------------

train_loader = DataLoader(
    train_dataset,
    batch_size=BATCH_SIZE,
    shuffle=True,
)

val_loader = DataLoader(
    val_dataset,
    batch_size=BATCH_SIZE,
    shuffle=False,
)


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
# Model
# -------------------------

model = WinProbabilityMLP(
    input_size=len(MODEL_FEATURES)
).to(device)

criterion = nn.BCEWithLogitsLoss()

optimizer = torch.optim.Adam(
    model.parameters(),
    lr=LEARNING_RATE,
)


# -------------------------
# Verify one batch
# -------------------------

X_batch, y_batch = next(
    iter(train_loader)
)

print(
    "X batch shape:",
    X_batch.shape,
)

print(
    "y batch shape:",
    y_batch.shape,
)

X_batch = X_batch.to(device)

logits = model(X_batch)

print(
    "Model output shape:",
    logits.shape,
)

print(
    "Initial logits:"
)

print(
    logits[:5]
)

probabilities = torch.sigmoid(
    logits
)

print(
    "Initial probabilities:"
)

print(
    probabilities[:5]
)


# -------------------------
# Early stopping state
# -------------------------

best_val_loss = float("inf")

epochs_without_improvement = 0

best_epoch = 0


# -------------------------
# Training / validation loop
# -------------------------

for epoch in range(EPOCHS):

    # -------------------------
    # Training
    # -------------------------

    model.train()

    total_train_loss = 0.0

    for X_batch, y_batch in train_loader:

        X_batch = X_batch.to(device)
        y_batch = y_batch.to(device)

        optimizer.zero_grad()

        logits = model(
            X_batch
        )

        loss = criterion(
            logits,
            y_batch,
        )

        loss.backward()

        optimizer.step()

        total_train_loss += (
            loss.item()
        )

    average_train_loss = (
        total_train_loss
        / len(train_loader)
    )


    # -------------------------
    # Validation
    # -------------------------

    model.eval()

    total_val_loss = 0.0

    all_probs = []
    all_labels = []

    with torch.no_grad():

        for X_batch, y_batch in val_loader:

            X_batch = X_batch.to(device)
            y_batch = y_batch.to(device)

            logits = model(
                X_batch
            )

            loss = criterion(
                logits,
                y_batch,
            )

            total_val_loss += (
                loss.item()
            )

            probabilities = torch.sigmoid(
                logits
            )

            all_probs.extend(
                probabilities
                .cpu()
                .numpy()
                .flatten()
            )

            all_labels.extend(
                y_batch
                .cpu()
                .numpy()
                .flatten()
            )

    average_val_loss = (
        total_val_loss
        / len(val_loader)
    )


    # -------------------------
    # Validation metrics
    # -------------------------

    val_predictions = [
        1 if probability >= 0.5 else 0
        for probability in all_probs
    ]

    accuracy = accuracy_score(
        all_labels,
        val_predictions,
    )

    logloss = log_loss(
        all_labels,
        all_probs,
    )

    brier = brier_score_loss(
        all_labels,
        all_probs,
    )

    auc = roc_auc_score(
        all_labels,
        all_probs,
    )


    # -------------------------
    # Epoch summary
    # -------------------------

    print(
        f"Epoch {epoch + 1}/{EPOCHS} | "
        f"train loss = {average_train_loss:.4f} | "
        f"val loss = {average_val_loss:.4f} | "
        f"accuracy = {accuracy:.4f} | "
        f"log loss = {logloss:.4f} | "
        f"brier = {brier:.4f} | "
        f"auc = {auc:.4f}"
    )


    # -------------------------
    # Save best model
    # -------------------------

    if average_val_loss < best_val_loss:

        best_val_loss = (
            average_val_loss
        )

        best_epoch = (
            epoch + 1
        )

        epochs_without_improvement = 0

        torch.save(
            model.state_dict(),
            MODEL_PATH,
        )

        print(
            f"Saved new best model "
            f"from epoch {best_epoch}"
        )

    else:

        epochs_without_improvement += 1

        print(
            "Epochs without improvement:",
            epochs_without_improvement,
        )


    # -------------------------
    # Early stopping
    # -------------------------

    if (
        epochs_without_improvement
        >= PATIENCE
    ):

        print(
            f"Early stopping after "
            f"epoch {epoch + 1}"
        )

        break


# -------------------------
# Reload best model
# -------------------------

print(
    "\nBest epoch:",
    best_epoch,
)

print(
    "Best validation loss:",
    f"{best_val_loss:.4f}",
)

model.load_state_dict(
    torch.load(
        MODEL_PATH,
        map_location=device,
    )
)

model.eval()


# -------------------------
# Final evaluation
# -------------------------

final_probs = []
final_labels = []

with torch.no_grad():

    for X_batch, y_batch in val_loader:

        X_batch = X_batch.to(device)
        y_batch = y_batch.to(device)

        logits = model(
            X_batch
        )

        probabilities = torch.sigmoid(
            logits
        )

        final_probs.extend(
            probabilities
            .cpu()
            .numpy()
            .flatten()
        )

        final_labels.extend(
            y_batch
            .cpu()
            .numpy()
            .flatten()
        )


final_predictions = [
    1 if probability >= 0.5 else 0
    for probability in final_probs
]


final_accuracy = accuracy_score(
    final_labels,
    final_predictions,
)

final_logloss = log_loss(
    final_labels,
    final_probs,
)

final_brier = brier_score_loss(
    final_labels,
    final_probs,
)

final_auc = roc_auc_score(
    final_labels,
    final_probs,
)


# -------------------------
# Final results
# -------------------------

print(
    "\nBest model validation metrics"
)

print(
    f"Accuracy:    {final_accuracy:.4f}"
)

print(
    f"Log loss:    {final_logloss:.4f}"
)

print(
    f"Brier score: {final_brier:.4f}"
)

print(
    f"ROC AUC:     {final_auc:.4f}"
)

print(
    "\nSaved model:",
    MODEL_PATH,
)

print(
    "Saved scaler:",
    SCALER_PATH,
)