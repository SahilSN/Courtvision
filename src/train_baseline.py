import pandas as pd
from sklearn.model_selection import train_test_split

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression

from sklearn.metrics import (
    accuracy_score,
    log_loss,
    brier_score_loss,
    roc_auc_score,
)

df = pd.read_csv("data/training/2024-25_training.csv")

game_ids = df["gameId"].unique()

train_games, val_games = train_test_split(
    game_ids,
    test_size=0.2,
    random_state=42,
)

train_df = df[df["gameId"].isin(train_games)].copy()
val_df = df[df["gameId"].isin(val_games)].copy()

print("Train games:", train_df["gameId"].nunique())
print("Validation games:", val_df["gameId"].nunique())

print("Train rows:", len(train_df))
print("Validation rows:", len(val_df))

FEATURES = [
    "elapsedGameTime",
    "homeScoreDiff",
    "homePossession",
]

TARGET = "homeWin"

X_train = train_df[FEATURES]
y_train = train_df[TARGET]

X_val = val_df[FEATURES]
y_val = val_df[TARGET]

model = Pipeline([
    ("scaler", StandardScaler()),
    ("model", LogisticRegression()),
])

model.fit(X_train, y_train)

val_prob = model.predict_proba(X_val)[:, 1]
val_pred = (val_prob >= 0.5).astype(int)

print("Accuracy:", accuracy_score(y_val, val_pred))
print("Log loss:", log_loss(y_val, val_prob))
print("Brier score:", brier_score_loss(y_val, val_prob))
print("ROC AUC:", roc_auc_score(y_val, val_prob))

game_id = val_games[0]

game = val_df[val_df["gameId"] == game_id].copy()

game["winProbability"] = model.predict_proba(
    game[FEATURES]
)[:, 1]

print(
    game[
        [
            "elapsedGameTime",
            "homeScoreDiff",
            "homePossession",
            "winProbability",
            "homeWin",
        ]
    ].head(30).to_string(index=False)
)