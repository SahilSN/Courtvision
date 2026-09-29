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
    grouped = list(
        game_df.groupby(
            "sequenceId",
            sort=False,
        )
    )

    rows = []

    for index, (
        sequence_id,
        sequence,
    ) in enumerate(
        grouped
    ):
        sequence = (
            sequence
            .copy()
            .reset_index(
                drop=True
            )
        )

        actual_post_state = (
            sequence
            .iloc[-1]
            .copy()
        )

        actual_probability = float(
            actual_post_state[
                "winProbability"
            ]
        )

        if index == 0:
            rows.append(
                {
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
            )

            continue

        previous_sequence = (
            grouped[
                index - 1
            ][1]
        )

        previous_state = (
            previous_sequence
            .iloc[-1]
            .copy()
        )

        previous_observed_probability = (
            float(
                previous_state[
                    "winProbability"
                ]
            )
        )

        counterfactual_state = (
            build_counterfactual_state(
                previous_state,
                actual_post_state,
            )
        )

        counterfactual_probability = (
            float(
                predict_states(
                    counterfactual_state,
                    model,
                    scaler,
                    device,
                )[0]
            )
        )

        # -------------------------
        # Core WPA v3 quantity
        # -------------------------
        #
        # Event effect:
        #
        # actual state at current time
        # minus
        # pre-event score/possession at
        # current time.
        #
        # Time is therefore held fixed.

        event_delta = (
            actual_probability
            - counterfactual_probability
        )

        # Old adjacent-state change.
        observed_delta = (
            actual_probability
            - previous_observed_probability
        )

        # Difference attributable to moving
        # the clock from the previous
        # sequence to the current sequence,
        # while leaving score/possession
        # unchanged.
        time_effect = (
            counterfactual_probability
            - previous_observed_probability
        )

        rows.append(
            {
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
    sequence,
    event_delta,
    home_team,
    away_team,
):
    candidates = (
        scoring_candidates(
            sequence
        )
    )

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
    # -------------------------
    # 1. Scoring
    # -------------------------

    scoring = (
        scoring_candidates(
            sequence
        )
    )

    if not scoring.empty:
        return (
            allocate_scoring_sequence(
                sequence,
                event_delta,
                home_team,
                away_team,
            )
        )

    # -------------------------
    # 2. Turnover
    # -------------------------

    turnovers = (
        turnover_candidates(
            sequence
        )
    )

    if not turnovers.empty:
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

    # -------------------------
    # 3. Rebound
    # -------------------------

    rebounds = (
        rebound_candidates(
            sequence
        )
    )

    if not rebounds.empty:
        rebound = (
            rebounds.tail(1)
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

    # -------------------------
    # 4. Missed shot
    # -------------------------

    misses = (
        missed_shot_candidates(
            sequence
        )
    )

    if not misses.empty:
        miss = (
            misses.head(1)
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
):
    season_df = (
        load_season_data(
            season
        )
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
            "WPA v3 same-time "
            "counterfactual"
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
