import argparse
import re
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch

from feature_engineering import (
    MODEL_FEATURES,
    add_model_features,
)
from model import WinProbabilityMLP

from shared_attribution import apply_shared_credit


# ============================================================
# Paths
# ============================================================

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

PROCESSED_DIR = (
    ROOT_DIR
    / "data"
    / "processed"
)

TRAINING_DIR = (
    ROOT_DIR
    / "data"
    / "training"
)

RESULTS_DIR = (
    ROOT_DIR
    / "results"
)


# ============================================================
# Basic helpers
# ============================================================

def normalize_game_id(game_id):
    return str(game_id).zfill(10)


def training_game_id(game_id):
    return int(
        normalize_game_id(
            game_id
        )
    )


def clean_text(value):
    if pd.isna(value):
        return ""

    return str(value).strip()


def format_clock(clock):
    clock = clean_text(clock)

    match = re.fullmatch(
        r"PT(?:(\d+)M)?(\d+(?:\.\d+)?)S",
        clock,
    )

    if match is None:
        return clock

    minutes = int(
        match.group(1)
        or 0
    )

    seconds = int(
        float(
            match.group(2)
        )
    )

    return (
        f"{minutes}:"
        f"{seconds:02d}"
    )


def infer_event_type(row):
    action_type = clean_text(
        row.get(
            "actionType",
            "",
        )
    )

    if action_type:
        return action_type

    description = (
        clean_text(
            row.get(
                "description",
                "",
            )
        )
        .upper()
    )

    if "BLOCK" in description:
        return "Block"

    if "STEAL" in description:
        return "Steal"

    return "Other"


# ============================================================
# Frozen V7
# ============================================================

def load_model():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Missing model: {MODEL_PATH}"
        )

    if not SCALER_PATH.exists():
        raise FileNotFoundError(
            f"Missing scaler: {SCALER_PATH}"
        )

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


def predict_states(
    df,
    model,
    scaler,
    device,
):
    if df.empty:
        return np.array([])

    X = df[
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

    return probabilities


# ============================================================
# Data loading
# ============================================================

def load_season_data(
    season,
):
    path = (
        TRAINING_DIR
        / (
            f"{season}"
            "_training_v4_base.csv"
        )
    )

    if not path.exists():
        raise FileNotFoundError(
            "Player WPA currently "
            "requires a local season "
            "training dataset.\n"
            f"Missing: {path}"
        )

    df = pd.read_csv(
        path
    )

    df = add_model_features(
        df
    )

    return df


def load_processed_game(
    game_id,
):
    game_id = (
        normalize_game_id(
            game_id
        )
    )

    path = (
        PROCESSED_DIR
        / f"{game_id}.csv"
    )

    if not path.exists():
        raise FileNotFoundError(
            "Missing processed "
            "play-by-play file:\n"
            f"{path}"
        )

    return pd.read_csv(
        path,
        dtype={
            "gameId": str,
        },
    )


def get_game_model_states(
    season_df,
    game_id,
):
    game_id_int = (
        training_game_id(
            game_id
        )
    )

    df = season_df[
        season_df[
            "gameId"
        ].astype(int)
        == game_id_int
    ].copy()

    if df.empty:
        raise ValueError(
            f"Game {game_id} "
            "was not found in "
            "the season dataset."
        )

    df = (
        df
        .sort_values(
            "elapsedGameTime",
            kind="mergesort",
        )
        .reset_index(
            drop=True
        )
    )

    return df


# ============================================================
# Add ordinary V7 probabilities
# ============================================================

def add_predictions(
    game_df,
    model,
    scaler,
    device,
):
    result = (
        game_df.copy()
    )

    result[
        "winProbability"
    ] = predict_states(
        result,
        model,
        scaler,
        device,
    )

    return result


# ============================================================
# PBP alignment
# ============================================================

def attach_play_by_play(
    prediction_df,
    processed_df,
):
    pbp = (
        processed_df
        .dropna(
            subset=[
                "homePossession",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    predictions = (
        prediction_df
        .reset_index(
            drop=True
        )
    )

    if len(pbp) != len(predictions):
        raise ValueError(
            "Prediction/PBP row mismatch: "
            f"{len(predictions)} "
            "prediction states vs "
            f"{len(pbp)} processed states."
        )

    metadata_columns = [
        "actionId",
        "actionNumber",
        "period",
        "clock",
        "teamId",
        "teamTricode",
        "personId",
        "playerName",
        "playerNameI",
        "actionType",
        "subType",
        "description",
        "scoreHome",
        "scoreAway",
    ]

    for column in (
        metadata_columns
    ):
        if column in pbp.columns:
            predictions[
                column
            ] = pbp[
                column
            ].to_numpy()

    predictions[
        "eventType"
    ] = predictions.apply(
        infer_event_type,
        axis=1,
    )

    return predictions


# ============================================================
# Team resolution
# ============================================================

def resolve_team_tricodes(
    game_df,
):
    home_id = int(
        game_df[
            "homeTeamId"
        ].iloc[0]
    )

    away_id = int(
        game_df[
            "awayTeamId"
        ].iloc[0]
    )

    team_lookup = {}

    for _, row in (
        game_df.iterrows()
    ):
        team_id = row.get(
            "teamId"
        )

        tricode = clean_text(
            row.get(
                "teamTricode",
                "",
            )
        )

        if pd.isna(team_id):
            continue

        team_id = int(team_id)

        if (
            team_id != 0
            and tricode
        ):
            team_lookup[
                team_id
            ] = tricode

    if home_id not in team_lookup:
        raise ValueError(
            "Unable to resolve "
            "home team tricode."
        )

    if away_id not in team_lookup:
        raise ValueError(
            "Unable to resolve "
            "away team tricode."
        )

    return (
        team_lookup[home_id],
        team_lookup[away_id],
    )


# ============================================================
# Same-clock grouping
# ============================================================

def add_sequence_ids(
    game_df,
):
    df = (
        game_df.copy()
    )

    period_changed = (
        df["period"]
        != df["period"].shift(1)
    )

    clock_changed = (
        df["clock"]
        != df["clock"].shift(1)
    )

    new_sequence = (
        period_changed
        | clock_changed
    )

    df[
        "sequenceId"
    ] = (
        new_sequence
        .cumsum()
        .astype(int)
    )

    return df


def add_row_score_changes(
    game_df,
):
    df = game_df.copy()

    df[
        "previousScoreHome"
    ] = (
        df[
            "scoreHome"
        ]
        .shift(1)
    )

    df[
        "previousScoreAway"
    ] = (
        df[
            "scoreAway"
        ]
        .shift(1)
    )

    df[
        "homePointsAdded"
    ] = (
        df["scoreHome"]
        - df[
            "previousScoreHome"
        ]
    )

    df[
        "awayPointsAdded"
    ] = (
        df["scoreAway"]
        - df[
            "previousScoreAway"
        ]
    )

    df[
        "homePointsAdded"
    ] = (
        df[
            "homePointsAdded"
        ]
        .fillna(0)
        .clip(lower=0)
    )

    df[
        "awayPointsAdded"
    ] = (
        df[
            "awayPointsAdded"
        ]
        .fillna(0)
        .clip(lower=0)
    )

    df[
        "pointsAdded"
    ] = (
        df[
            "homePointsAdded"
        ]
        + df[
            "awayPointsAdded"
        ]
    )

    return df


# ============================================================
# Counterfactual state construction
# ============================================================

def recompute_dependent_features(
    state,
):
    state = (
        state.copy()
    )

    state[
        "homeScoreDiff"
    ] = (
        state[
            "scoreHome"
        ]
        - state[
            "scoreAway"
        ]
    )

    state[
        "totalScore"
    ] = (
        state[
            "scoreHome"
        ]
        + state[
            "scoreAway"
        ]
    )

    regulation_progress = (
        state[
            "elapsedGameTime"
        ]
        / 2880.0
    ).clip(
        lower=0.0,
        upper=1.0,
    )

    state[
        "scoreDiffLateWeight"
    ] = (
        state[
            "homeScoreDiff"
        ]
        * regulation_progress
    )

    return state


def build_counterfactual_state(
    previous_state,
    actual_post_state,
):
    """
    Construct the state that would exist at
    the CURRENT timestamp if the new
    basketball sequence had not yet changed
    score or possession.

    Time and pregame information come from
    the actual current state.

    Score and possession come from the
    preceding sequence.
    """

    counterfactual = (
        actual_post_state
        .copy()
        .to_frame()
        .T
    )

    counterfactual[
        "scoreHome"
    ] = int(
        previous_state[
            "scoreHome"
        ]
    )

    counterfactual[
        "scoreAway"
    ] = int(
        previous_state[
            "scoreAway"
        ]
    )

    counterfactual[
        "homePossession"
    ] = int(
        previous_state[
            "homePossession"
        ]
    )

    counterfactual = (
        recompute_dependent_features(
            counterfactual
        )
    )

    # Force model features back to numeric.
    for feature in (
        MODEL_FEATURES
    ):
        counterfactual[
            feature
        ] = pd.to_numeric(
            counterfactual[
                feature
            ],
            errors="raise",
        )

    return counterfactual


# ============================================================
# Counterfactual sequence table
# ============================================================

def build_sequence_table(
    game_df,
    model,
    scaler,
    device,
):
    """
    Build the frozen WPA v3 same-time counterfactual table.

    Semantics are unchanged from the original implementation,
    but all counterfactual V7 states are predicted in one batch
    rather than one model call per sequence.
    """

    grouped = list(
        game_df.groupby(
            "sequenceId",
            sort=False,
        )
    )

    if not grouped:
        return pd.DataFrame()

    sequence_metadata = []
    counterfactual_features = []

    # --------------------------------------------------------
    # First pass:
    # collect sequence metadata and construct only the eight
    # V7 features needed for each same-time counterfactual.
    # --------------------------------------------------------

    for index, (
        sequence_id,
        sequence,
    ) in enumerate(
        grouped
    ):
        actual_post_state = (
            sequence.iloc[-1]
        )

        actual_probability = float(
            actual_post_state[
                "winProbability"
            ]
        )

        metadata = {
            "sequenceId":
                sequence_id,

            "period":
                int(
                    sequence[
                        "period"
                    ].iloc[0]
                ),

            "clock":
                sequence[
                    "clock"
                ].iloc[0],

            "elapsedGameTime":
                float(
                    actual_post_state[
                        "elapsedGameTime"
                    ]
                ),

            "rowsInSequence":
                len(sequence),

            "actualWinProbability":
                actual_probability,

            "scoreHome":
                int(
                    actual_post_state[
                        "scoreHome"
                    ]
                ),

            "scoreAway":
                int(
                    actual_post_state[
                        "scoreAway"
                    ]
                ),

            "homePossession":
                int(
                    actual_post_state[
                        "homePossession"
                    ]
                ),
        }

        if index == 0:
            metadata[
                "previousObservedWinProbability"
            ] = np.nan

            sequence_metadata.append(
                metadata
            )

            continue

        previous_state = (
            grouped[
                index - 1
            ][1]
            .iloc[-1]
        )

        previous_observed_probability = float(
            previous_state[
                "winProbability"
            ]
        )

        metadata[
            "previousObservedWinProbability"
        ] = (
            previous_observed_probability
        )

        sequence_metadata.append(
            metadata
        )

        # Same WPA v3 counterfactual as before:
        #
        # CURRENT time/pregame context
        # PREVIOUS score/possession.
        elapsed = float(
            actual_post_state[
                "elapsedGameTime"
            ]
        )

        score_home = int(
            previous_state[
                "scoreHome"
            ]
        )

        score_away = int(
            previous_state[
                "scoreAway"
            ]
        )

        home_score_diff = (
            score_home
            - score_away
        )

        total_score = (
            score_home
            + score_away
        )

        regulation_progress = min(
            1.0,
            max(
                0.0,
                elapsed / 2880.0,
            ),
        )

        counterfactual_features.append(
            {
                "elapsedGameTime":
                    elapsed,

                "homeScoreDiff":
                    home_score_diff,

                "homePossession":
                    int(
                        previous_state[
                            "homePossession"
                        ]
                    ),

                "totalScore":
                    total_score,

                "homePreGameWinPct":
                    float(
                        actual_post_state[
                            "homePreGameWinPct"
                        ]
                    ),

                "awayPreGameWinPct":
                    float(
                        actual_post_state[
                            "awayPreGameWinPct"
                        ]
                    ),

                "strengthDifference":
                    float(
                        actual_post_state[
                            "strengthDifference"
                        ]
                    ),

                "scoreDiffLateWeight":
                    (
                        home_score_diff
                        * regulation_progress
                    ),
            }
        )

    # --------------------------------------------------------
    # One scaler transform + one V7 forward pass for all
    # counterfactual sequence states.
    # --------------------------------------------------------

    if counterfactual_features:
        counterfactual_df = pd.DataFrame(
            counterfactual_features,
            columns=MODEL_FEATURES,
        )

        counterfactual_probabilities = (
            predict_states(
                counterfactual_df,
                model,
                scaler,
                device,
            )
        )

    else:
        counterfactual_probabilities = (
            np.array([])
        )

    # --------------------------------------------------------
    # Second pass:
    # reconstruct the exact frozen WPA v3 output schema.
    # --------------------------------------------------------

    rows = []
    counterfactual_index = 0

    for index, metadata in enumerate(
        sequence_metadata
    ):
        actual_probability = float(
            metadata[
                "actualWinProbability"
            ]
        )

        if index == 0:
            rows.append(
                {
                    "sequenceId":
                        metadata[
                            "sequenceId"
                        ],

                    "period":
                        metadata[
                            "period"
                        ],

                    "clock":
                        metadata[
                            "clock"
                        ],

                    "elapsedGameTime":
                        metadata[
                            "elapsedGameTime"
                        ],

                    "rowsInSequence":
                        metadata[
                            "rowsInSequence"
                        ],

                    "counterfactualWinProbability":
                        np.nan,

                    "actualWinProbability":
                        actual_probability,

                    "eventHomeWinProbabilityChange":
                        np.nan,

                    "previousObservedWinProbability":
                        np.nan,

                    "observedAdjacentChange":
                        np.nan,

                    "timeEffect":
                        np.nan,

                    "scoreHome":
                        metadata[
                            "scoreHome"
                        ],

                    "scoreAway":
                        metadata[
                            "scoreAway"
                        ],

                    "homePossession":
                        metadata[
                            "homePossession"
                        ],
                }
            )

            continue

        counterfactual_probability = float(
            counterfactual_probabilities[
                counterfactual_index
            ]
        )

        counterfactual_index += 1

        previous_observed_probability = float(
            metadata[
                "previousObservedWinProbability"
            ]
        )

        event_delta = (
            actual_probability
            - counterfactual_probability
        )

        observed_delta = (
            actual_probability
            - previous_observed_probability
        )

        time_effect = (
            counterfactual_probability
            - previous_observed_probability
        )

        rows.append(
            {
                "sequenceId":
                    metadata[
                        "sequenceId"
                    ],

                "period":
                    metadata[
                        "period"
                    ],

                "clock":
                    metadata[
                        "clock"
                    ],

                "elapsedGameTime":
                    metadata[
                        "elapsedGameTime"
                    ],

                "rowsInSequence":
                    metadata[
                        "rowsInSequence"
                    ],

                "counterfactualWinProbability":
                    counterfactual_probability,

                "actualWinProbability":
                    actual_probability,

                "eventHomeWinProbabilityChange":
                    event_delta,

                "previousObservedWinProbability":
                    previous_observed_probability,

                "observedAdjacentChange":
                    observed_delta,

                "timeEffect":
                    time_effect,

                "scoreHome":
                    metadata[
                        "scoreHome"
                    ],

                "scoreAway":
                    metadata[
                        "scoreAway"
                    ],

                "homePossession":
                    metadata[
                        "homePossession"
                    ],
            }
        )

    return pd.DataFrame(
        rows
    )


# ============================================================
# Attribution candidate helpers
# ============================================================

def valid_player_row(
    row,
):
    return bool(
        clean_text(
            row.get(
                "playerName",
                "",
            )
        )
        and clean_text(
            row.get(
                "teamTricode",
                "",
            )
        )
    )


def scoring_candidates(
    sequence,
):
    mask = (
        sequence[
            "eventType"
        ].isin(
            [
                "Made Shot",
                "Free Throw",
            ]
        )
        & (
            sequence[
                "pointsAdded"
            ]
            > 0
        )
    )

    candidates = (
        sequence[
            mask
        ].copy()
    )

    if candidates.empty:
        return candidates

    return candidates[
        candidates.apply(
            valid_player_row,
            axis=1,
        )
    ]


def turnover_candidates(
    sequence,
):
    candidates = (
        sequence[
            sequence[
                "eventType"
            ]
            == "Turnover"
        ]
        .copy()
    )

    return candidates[
        candidates.apply(
            valid_player_row,
            axis=1,
        )
    ]


def rebound_candidates(
    sequence,
):
    candidates = (
        sequence[
            sequence[
                "eventType"
            ]
            == "Rebound"
        ]
        .copy()
    )

    return candidates[
        candidates.apply(
            valid_player_row,
            axis=1,
        )
    ]


def missed_shot_candidates(
    sequence,
):
    candidates = (
        sequence[
            sequence[
                "eventType"
            ]
            == "Missed Shot"
        ]
        .copy()
    )

    return candidates[
        candidates.apply(
            valid_player_row,
            axis=1,
        )
    ]


# ============================================================
# Team-relative conversion
# ============================================================

def team_relative_delta(
    home_delta,
    team,
    home_team,
    away_team,
):
    if pd.isna(
        home_delta
    ):
        return np.nan

    if team == home_team:
        return float(
            home_delta
        )

    if team == away_team:
        return float(
            -home_delta
        )

    return np.nan


# ============================================================
# WPA allocation
# ============================================================

def allocate_scoring_sequence(
    candidates,
    event_delta,
    home_team,
    away_team,
):
    """
    Allocate an already-classified same-clock scoring
    sequence.

    Candidate discovery is intentionally performed once
    in choose_sequence_attribution() rather than repeated
    here.
    """

    if candidates.empty:
        return []

    total_points = (
        candidates[
            "pointsAdded"
        ].sum()
    )

    if total_points <= 0:
        return []

    allocations = []

    for _, row in (
        candidates.iterrows()
    ):
        weight = float(
            row[
                "pointsAdded"
            ]
            / total_points
        )

        team = clean_text(
            row[
                "teamTricode"
            ]
        )

        relative_delta = (
            team_relative_delta(
                event_delta,
                team,
                home_team,
                away_team,
            )
        )

        allocations.append(
            {
                "row":
                    row,

                "weight":
                    weight,

                "playerWPA":
                    (
                        relative_delta
                        * weight
                    ),

                "attributionType":
                    "Scoring",

                "attributionReason":
                    (
                        "same-clock scoring "
                        "sequence"
                    ),
            }
        )

    return allocations


def allocate_equal_candidates(
    candidates,
    event_delta,
    home_team,
    away_team,
    attribution_type,
    reason,
):
    if candidates.empty:
        return []

    weight = (
        1.0
        / len(candidates)
    )

    allocations = []

    for _, row in (
        candidates.iterrows()
    ):
        team = clean_text(
            row[
                "teamTricode"
            ]
        )

        relative_delta = (
            team_relative_delta(
                event_delta,
                team,
                home_team,
                away_team,
            )
        )

        allocations.append(
            {
                "row":
                    row,

                "weight":
                    weight,

                "playerWPA":
                    (
                        relative_delta
                        * weight
                    ),

                "attributionType":
                    attribution_type,

                "attributionReason":
                    reason,
            }
        )

    return allocations


def choose_sequence_attribution(
    sequence,
    event_delta,
    home_team,
    away_team,
):
    """
    Choose the frozen WPA v3 attribution target.

    Priority is unchanged:
      1. scoring
      2. turnover
      3. last valid rebound
      4. first valid missed shot

    Player validity is computed once for the sequence rather
    than repeatedly through DataFrame.apply(axis=1).
    """

    if sequence.empty:
        return []

    # Equivalent to valid_player_row():
    #
    # clean_text(playerName)
    # AND
    # clean_text(teamTricode)
    #
    # Both fields must be non-null and non-blank.
    valid_mask = (
        sequence[
            "playerName"
        ]
        .fillna("")
        .astype(str)
        .str.strip()
        .ne("")
        &
        sequence[
            "teamTricode"
        ]
        .fillna("")
        .astype(str)
        .str.strip()
        .ne("")
    )

    event_types = (
        sequence[
            "eventType"
        ]
    )

    # --------------------------------------------------------
    # 1. Scoring
    # --------------------------------------------------------

    scoring_mask = (
        valid_mask
        & event_types.isin(
            [
                "Made Shot",
                "Free Throw",
            ]
        )
        & (
            sequence[
                "pointsAdded"
            ]
            > 0
        )
    )

    if scoring_mask.any():
        scoring = (
            sequence.loc[
                scoring_mask
            ]
        )

        return (
            allocate_scoring_sequence(
                scoring,
                event_delta,
                home_team,
                away_team,
            )
        )

    # --------------------------------------------------------
    # 2. Turnover
    # --------------------------------------------------------

    turnover_mask = (
        valid_mask
        & (
            event_types
            == "Turnover"
        )
    )

    if turnover_mask.any():
        turnovers = (
            sequence.loc[
                turnover_mask
            ]
        )

        return (
            allocate_equal_candidates(
                turnovers,
                event_delta,
                home_team,
                away_team,
                "Turnover",
                "same-clock turnover sequence",
            )
        )

    # --------------------------------------------------------
    # 3. Rebound
    # --------------------------------------------------------

    rebound_mask = (
        valid_mask
        & (
            event_types
            == "Rebound"
        )
    )

    if rebound_mask.any():
        rebound = (
            sequence.loc[
                rebound_mask
            ]
            .tail(1)
        )

        return (
            allocate_equal_candidates(
                rebound,
                event_delta,
                home_team,
                away_team,
                "Rebound",
                (
                    "rebound established "
                    "post-sequence possession"
                ),
            )
        )

    # --------------------------------------------------------
    # 4. Missed shot
    # --------------------------------------------------------

    miss_mask = (
        valid_mask
        & (
            event_types
            == "Missed Shot"
        )
    )

    if miss_mask.any():
        miss = (
            sequence.loc[
                miss_mask
            ]
            .head(1)
        )

        return (
            allocate_equal_candidates(
                miss,
                event_delta,
                home_team,
                away_team,
                "Missed Shot",
                (
                    "same-clock missed-shot "
                    "sequence"
                ),
            )
        )

    return []


# ============================================================
# Build WPA events
# ============================================================

def build_player_wpa_events(
    game_df,
    model,
    scaler,
    device,
):
    df = (
        add_sequence_ids(
            game_df
        )
    )

    df = (
        add_row_score_changes(
            df
        )
    )

    (
        home_team,
        away_team,
    ) = resolve_team_tricodes(
        df
    )

    sequence_table = (
        build_sequence_table(
            df,
            model,
            scaler,
            device,
        )
    )

    sequence_lookup = (
        sequence_table
        .set_index(
            "sequenceId"
        )
        .to_dict(
            orient="index"
        )
    )

    event_rows = []

    for (
        sequence_id,
        sequence,
    ) in df.groupby(
        "sequenceId",
        sort=False,
    ):
        sequence_info = (
            sequence_lookup[
                sequence_id
            ]
        )

        event_delta = (
            sequence_info[
                "eventHomeWinProbabilityChange"
            ]
        )

        if pd.isna(
            event_delta
        ):
            continue

        allocations = (
            choose_sequence_attribution(
                sequence,
                event_delta,
                home_team,
                away_team,
            )
        )

        for allocation in (
            allocations
        ):
            row = (
                allocation[
                    "row"
                ]
            )

            player_wpa = (
                allocation[
                    "playerWPA"
                ]
            )

            if pd.isna(
                player_wpa
            ):
                continue

            event_rows.append(
                {
                    "sequenceId":
                        sequence_id,

                    "period":
                        int(
                            sequence_info[
                                "period"
                            ]
                        ),

                    "clock":
                        sequence_info[
                            "clock"
                        ],

                    "elapsedGameTime":
                        float(
                            sequence_info[
                                "elapsedGameTime"
                            ]
                        ),

                    "rowsInSequence":
                        int(
                            sequence_info[
                                "rowsInSequence"
                            ]
                        ),

                    "teamId":
                        row.get(
                            "teamId"
                        ),

                    "teamTricode":
                        clean_text(
                            row.get(
                                "teamTricode",
                                "",
                            )
                        ),

                    "personId":
                        row.get(
                            "personId"
                        ),

                    "playerName":
                        clean_text(
                            row.get(
                                "playerName",
                                "",
                            )
                        ),

                    "eventType":
                        infer_event_type(
                            row
                        ),

                    "subType":
                        clean_text(
                            row.get(
                                "subType",
                                "",
                            )
                        ),

                    "description":
                        clean_text(
                            row.get(
                                "description",
                                "",
                            )
                        ),

                    "attributionType":
                        allocation[
                            "attributionType"
                        ],

                    "attributionReason":
                        allocation[
                            "attributionReason"
                        ],

                    "allocationWeight":
                        float(
                            allocation[
                                "weight"
                            ]
                        ),

                    # -------------------------
                    # Counterfactual quantities
                    # -------------------------

                    "counterfactualWinProbability":
                        sequence_info[
                            "counterfactualWinProbability"
                        ],

                    "actualWinProbability":
                        sequence_info[
                            "actualWinProbability"
                        ],

                    "eventHomeWinProbabilityChange":
                        event_delta,

                    "observedAdjacentChange":
                        sequence_info[
                            "observedAdjacentChange"
                        ],

                    "timeEffect":
                        sequence_info[
                            "timeEffect"
                        ],

                    # -------------------------
                    # Player-relative WPA
                    # -------------------------

                    "playerWPA":
                        player_wpa,

                    "playerWPAPoints":
                        (
                            player_wpa
                            * 100.0
                        ),

                    "scoreHome":
                        sequence_info[
                            "scoreHome"
                        ],

                    "scoreAway":
                        sequence_info[
                            "scoreAway"
                        ],
                }
            )

    events = pd.DataFrame(
        event_rows
    )

    return (
        events,
        sequence_table,
        home_team,
        away_team,
    )


# ============================================================
# Player summary
# ============================================================

def summarize_players(
    events,
):
    if events.empty:
        return pd.DataFrame(
            columns=[
                "personId",
                "playerName",
                "teamTricode",
                "events",
                "netWPA",
                "positiveWPA",
                "negativeWPA",
                "absoluteWPA",
            ]
        )

    df = (
        events.copy()
    )

    df[
        "positiveWPA"
    ] = (
        df[
            "playerWPA"
        ]
        .clip(
            lower=0.0
        )
    )

    df[
        "negativeWPA"
    ] = (
        df[
            "playerWPA"
        ]
        .clip(
            upper=0.0
        )
    )

    df[
        "absoluteWPA"
    ] = (
        df[
            "playerWPA"
        ]
        .abs()
    )

    summary = (
        df.groupby(
            [
                "personId",
                "playerName",
                "teamTricode",
            ],
            dropna=False,
        )
        .agg(
            events=(
                "playerWPA",
                "size",
            ),

            netWPA=(
                "playerWPA",
                "sum",
            ),

            positiveWPA=(
                "positiveWPA",
                "sum",
            ),

            negativeWPA=(
                "negativeWPA",
                "sum",
            ),

            absoluteWPA=(
                "absoluteWPA",
                "sum",
            ),

            maxPositiveEvent=(
                "playerWPA",
                "max",
            ),

            maxNegativeEvent=(
                "playerWPA",
                "min",
            ),
        )
        .reset_index()
    )

    summary[
        "netWPAPoints"
    ] = (
        summary[
            "netWPA"
        ]
        * 100.0
    )

    summary[
        "positiveWPAPoints"
    ] = (
        summary[
            "positiveWPA"
        ]
        * 100.0
    )

    summary[
        "negativeWPAPoints"
    ] = (
        summary[
            "negativeWPA"
        ]
        * 100.0
    )

    summary[
        "absoluteWPAPoints"
    ] = (
        summary[
            "absoluteWPA"
        ]
        * 100.0
    )

    summary[
        "maxPositiveEventPoints"
    ] = (
        summary[
            "maxPositiveEvent"
        ]
        * 100.0
    )

    summary[
        "maxNegativeEventPoints"
    ] = (
        summary[
            "maxNegativeEvent"
        ]
        * 100.0
    )

    return (
        summary
        .sort_values(
            [
                "netWPA",
                "absoluteWPA",
            ],
            ascending=[
                False,
                False,
            ],
            kind="mergesort",
        )
        .reset_index(
            drop=True
        )
    )


# ============================================================
# Biggest events
# ============================================================

def biggest_events(
    events,
    top_k=10,
):
    if events.empty:
        return events.copy()

    df = events.copy()

    df[
        "absoluteWPA"
    ] = (
        df[
            "playerWPA"
        ]
        .abs()
    )

    return (
        df.nlargest(
            top_k,
            "absoluteWPA",
        )
        .reset_index(
            drop=True
        )
    )


# ============================================================
# Diagnostics
# ============================================================

def build_attribution_diagnostics(
    events,
    sequence_table,
):
    valid_sequences = (
        sequence_table[
            sequence_table[
                "eventHomeWinProbabilityChange"
            ].notna()
        ]
    )

    total_sequences = len(
        valid_sequences
    )

    attributed_sequences = (
        events[
            "sequenceId"
        ].nunique()
        if not events.empty
        else 0
    )

    total_event_movement = (
        valid_sequences[
            "eventHomeWinProbabilityChange"
        ]
        .abs()
        .sum()
    )

    if events.empty:
        attributed_event_movement = 0.0
    else:
        attributed_ids = (
            events[
                "sequenceId"
            ].unique()
        )

        attributed_event_movement = (
            valid_sequences[
                valid_sequences[
                    "sequenceId"
                ].isin(
                    attributed_ids
                )
            ][
                "eventHomeWinProbabilityChange"
            ]
            .abs()
            .sum()
        )

    total_observed_movement = (
        valid_sequences[
            "observedAdjacentChange"
        ]
        .abs()
        .sum()
    )

    total_time_effect = (
        valid_sequences[
            "timeEffect"
        ]
        .abs()
        .sum()
    )

    return {
        "clock_sequences":
            total_sequences,

        "attributed_sequences":
            attributed_sequences,

        "sequence_coverage":
            (
                attributed_sequences
                / total_sequences
                if total_sequences
                else np.nan
            ),

        "absolute_event_effect":
            float(
                total_event_movement
            ),

        "attributed_absolute_event_effect":
            float(
                attributed_event_movement
            ),

        "event_effect_coverage":
            (
                float(
                    attributed_event_movement
                    / total_event_movement
                )
                if total_event_movement > 0
                else np.nan
            ),

        "absolute_adjacent_change":
            float(
                total_observed_movement
            ),

        "absolute_time_effect":
            float(
                total_time_effect
            ),
    }


# ============================================================
# Printing
# ============================================================

def print_summary(
    summary,
    home_team,
    away_team,
    top_k,
):
    print()
    print(
        "=" * 100
    )
    print(
        "Player Win Probability Added — WPA v3"
    )
    print(
        "=" * 100
    )

    print(
        f"Home: {home_team}"
    )

    print(
        f"Away: {away_team}"
    )

    if summary.empty:
        print(
            "No attributable "
            "player events."
        )
        return

    display = (
        summary[
            [
                "playerName",
                "teamTricode",
                "events",
                "netWPAPoints",
                "positiveWPAPoints",
                "negativeWPAPoints",
                "absoluteWPAPoints",
            ]
        ]
        .head(
            top_k
        )
        .copy()
    )

    display = (
        display.rename(
            columns={
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
            }
        )
    )

    print(
        display.to_string(
            index=False,
            float_format=lambda x:
                f"{x:+.2f}",
        )
    )


def print_events(
    events,
):
    print()
    print(
        "=" * 100
    )
    print(
        "Largest Counterfactual Player WPA Events"
    )
    print(
        "=" * 100
    )

    if events.empty:
        print(
            "No attributable events."
        )
        return

    for _, row in (
        events.iterrows()
    ):
        clock = format_clock(
            row[
                "clock"
            ]
        )

        before = (
            row[
                "counterfactualWinProbability"
            ]
            * 100
        )

        after = (
            row[
                "actualWinProbability"
            ]
            * 100
        )

        event_pp = (
            row[
                "eventHomeWinProbabilityChange"
            ]
            * 100
        )

        time_pp = (
            row[
                "timeEffect"
            ]
            * 100
        )

        print(
            f"Q{int(row['period'])} "
            f"{clock} | "
            f"{row['teamTricode']} | "
            f"{row['playerName']} | "
            f"{row['playerWPAPoints']:+.2f} pp | "
            f"{row['attributionType']}"
        )

        print(
            "  "
            f"{row['description']}"
        )

        print(
            "  "
            f"Same-time counterfactual: "
            f"{before:.1f}% -> "
            f"{after:.1f}% "
            f"({event_pp:+.1f} home pp)"
        )

        print(
            "  "
            f"Clock-only effect since "
            f"previous sequence: "
            f"{time_pp:+.1f} home pp"
        )

        if (
            row[
                "rowsInSequence"
            ]
            > 1
        ):
            print(
                "  "
                f"Grouped "
                f"{int(row['rowsInSequence'])} "
                "same-clock PBP rows."
            )


def print_diagnostics(
    diagnostics,
):
    print()
    print(
        "=" * 100
    )
    print(
        "Counterfactual Attribution Diagnostics"
    )
    print(
        "=" * 100
    )

    print(
        "Clock sequences:",
        diagnostics[
            "clock_sequences"
        ],
    )

    print(
        "Attributed sequences:",
        diagnostics[
            "attributed_sequences"
        ],
    )

    print(
        "Sequence coverage:",
        (
            f"{diagnostics['sequence_coverage'] * 100:.1f}%"
        ),
    )

    print(
        "Counterfactual event-effect coverage:",
        (
            f"{diagnostics['event_effect_coverage'] * 100:.1f}%"
        ),
    )

    print(
        "Total absolute adjacent-state movement:",
        (
            f"{diagnostics['absolute_adjacent_change'] * 100:.2f} pp"
        ),
    )

    print(
        "Total absolute counterfactual event effect:",
        (
            f"{diagnostics['absolute_event_effect'] * 100:.2f} pp"
        ),
    )

    print(
        "Total absolute clock-only effect:",
        (
            f"{diagnostics['absolute_time_effect'] * 100:.2f} pp"
        ),
    )


# ============================================================
# Main analysis API
# ============================================================

def analyze_player_impact(
    game_id,
    season,
    top_k=10,
    season_df=None,
    model=None,
    scaler=None,
    device=None,
):
    if season_df is None:
        season_df = (
            load_season_data(
                season
            )
        )

    provided_model_artifacts = [
        model is not None,
        scaler is not None,
        device is not None,
    ]

    if (
        any(provided_model_artifacts)
        and not all(provided_model_artifacts)
    ):
        raise ValueError(
            "model, scaler, and device must either "
            "all be supplied or all be omitted."
        )

    processed_df = (
        load_processed_game(
            game_id
        )
    )

    game_df = (
        get_game_model_states(
            season_df,
            game_id,
        )
    )

    if model is None:
        (
            model,
            scaler,
            device,
        ) = load_model()

    game_df = (
        add_predictions(
            game_df,
            model,
            scaler,
            device,
        )
    )

    game_df = (
        attach_play_by_play(
            game_df,
            processed_df,
        )
    )

    (
        events,
        sequence_table,
        home_team,
        away_team,
    ) = (
        build_player_wpa_events(
            game_df,
            model,
            scaler,
            device,
        )
    )

    # --------------------------------------------------------
    # Shared-credit attribution
    #
    # The counterfactual WPA v3 event values above remain
    # frozen. This layer only redistributes attribution among
    # scorer/assister, turnover/stealer, and shooter/blocker.
    # --------------------------------------------------------

    events = apply_shared_credit(
        events,
        game_df,
        home_team,
        away_team,
    )

    summary = (
        summarize_players(
            events
        )
    )

    top_events = (
        biggest_events(
            events,
            top_k=top_k,
        )
    )

    diagnostics = (
        build_attribution_diagnostics(
            events,
            sequence_table,
        )
    )

    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    normalized_id = (
        normalize_game_id(
            game_id
        )
    )

    summary_path = (
        RESULTS_DIR
        / (
            f"player_wpa_v3_"
            f"{normalized_id}"
            "_summary.csv"
        )
    )

    events_path = (
        RESULTS_DIR
        / (
            f"player_wpa_v3_"
            f"{normalized_id}"
            "_events.csv"
        )
    )

    sequences_path = (
        RESULTS_DIR
        / (
            f"player_wpa_v3_"
            f"{normalized_id}"
            "_sequences.csv"
        )
    )

    summary.to_csv(
        summary_path,
        index=False,
    )

    events.to_csv(
        events_path,
        index=False,
    )

    sequence_table.to_csv(
        sequences_path,
        index=False,
    )

    print()
    print(
        "Courtvision Player Impact"
    )

    print(
        "Game:",
        normalized_id,
    )

    print(
        "Season:",
        season,
    )

    print(
        "Model:",
        "Frozen V7",
    )

    print(
        "Attribution:",
        (
            "WPA v3 counterfactual "
            "+ shared credit"
        ),
    )

    print(
        "Device:",
        device,
    )

    print_summary(
        summary,
        home_team,
        away_team,
        top_k,
    )

    print_events(
        top_events
    )

    print_diagnostics(
        diagnostics
    )

    print()
    print(
        "Saved:"
    )

    print(
        " ",
        summary_path,
    )

    print(
        " ",
        events_path,
    )

    print(
        " ",
        sequences_path,
    )

    return {
        "game_df":
            game_df,

        "player_summary":
            summary,

        "events":
            events,

        "biggest_events":
            top_events,

        "sequences":
            sequence_table,

        "home_team":
            home_team,

        "away_team":
            away_team,

        "diagnostics":
            diagnostics,
    }


# ============================================================
# CLI
# ============================================================

def parse_args():
    parser = (
        argparse.ArgumentParser(
            description=(
                "Compute same-time "
                "counterfactual player "
                "WPA using frozen "
                "Courtvision V7."
            )
        )
    )

    parser.add_argument(
        "game_id",
        help=(
            "NBA game ID, e.g. "
            "0022400500."
        ),
    )

    parser.add_argument(
        "--season",
        default="2024-25",
        help=(
            "NBA season containing "
            "the game."
        ),
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help=(
            "Number of players and "
            "events to display."
        ),
    )

    return parser.parse_args()


def main():
    args = (
        parse_args()
    )

    analyze_player_impact(
        game_id=(
            args.game_id
        ),
        season=(
            args.season
        ),
        top_k=(
            args.top_k
        ),
    )


if __name__ == "__main__":
    main()
