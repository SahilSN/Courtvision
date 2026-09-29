import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT_DIR / "results"


def expected_calibration_error(
    labels,
    probabilities,
    n_bins=10,
    weights=None,
):
    labels = np.asarray(labels, dtype=float)
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

    bin_edges = np.linspace(
        0.0,
        1.0,
        n_bins + 1,
    )

    total_weight = weights.sum()
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

        bin_weights = weights[mask]

        mean_prediction = np.average(
            probabilities[mask],
            weights=bin_weights,
        )

        observed_rate = np.average(
            labels[mask],
            weights=bin_weights,
        )

        ece += (
            bin_weights.sum()
            / total_weight
        ) * abs(
            mean_prediction
            - observed_rate
        )

    return float(ece)


def game_balanced_weights(df):
    rows_per_game = (
        df.groupby("gameId")["gameId"]
        .transform("count")
        .to_numpy()
    )

    return 1.0 / rows_per_game


def calculate_metrics(
    df,
    weights=None,
):
    labels = (
        df["homeWin"]
        .astype(int)
        .to_numpy()
    )

    probabilities = (
        df["winProbability"]
        .astype(float)
        .to_numpy()
    )

    predictions = (
        probabilities >= 0.5
    ).astype(int)

    if weights is None:
        accuracy = accuracy_score(
            labels,
            predictions,
        )
    else:
        accuracy = np.average(
            predictions == labels,
            weights=weights,
        )

    if len(np.unique(labels)) >= 2:
        auc = roc_auc_score(
            labels,
            probabilities,
            sample_weight=weights,
        )
    else:
        auc = np.nan

    return {
        "games":
            df["gameId"].nunique(),

        "states":
            len(df),

        "accuracy":
            float(accuracy),

        "log_loss":
            float(
                log_loss(
                    labels,
                    probabilities,
                    sample_weight=weights,
                )
            ),

        "brier":
            float(
                brier_score_loss(
                    labels,
                    probabilities,
                    sample_weight=weights,
                )
            ),

        "auc":
            float(auc),

        "ece":
            expected_calibration_error(
                labels,
                probabilities,
                weights=weights,
            ),
    }


def add_game_phase(df):
    df = df.copy()

    elapsed = df[
        "elapsedGameTime"
    ]

    df["gamePhase"] = pd.cut(
        elapsed,
        bins=[
            -np.inf,
            720,
            1440,
            2160,
            np.inf,
        ],
        labels=[
            "Q1",
            "Q2",
            "Q3",
            "Q4+",
        ],
        right=True,
    )

    return df


def build_phase_metrics(df):
    rows = []

    for phase, group in df.groupby(
        "gamePhase",
        observed=True,
    ):
        state_metrics = calculate_metrics(
            group
        )

        balanced_metrics = calculate_metrics(
            group,
            weights=game_balanced_weights(
                group
            ),
        )

        rows.append(
            {
                "phase": str(phase),
                "weighting": "state",
                **state_metrics,
            }
        )

        rows.append(
            {
                "phase": str(phase),
                "weighting":
                    "game_balanced",
                **balanced_metrics,
            }
        )

    return pd.DataFrame(rows)


def build_calibration_bins(df):
    df = df.copy()

    edges = np.linspace(
        0.0,
        1.0,
        11,
    )

    df["probabilityBin"] = pd.cut(
        df["winProbability"],
        bins=edges,
        include_lowest=True,
    )

    rows = []

    for interval, group in df.groupby(
        "probabilityBin",
        observed=True,
    ):
        predicted = float(
            group[
                "winProbability"
            ].mean()
        )

        observed = float(
            group[
                "homeWin"
            ].mean()
        )

        rows.append(
            {
                "bin":
                    str(interval),

                "games":
                    group[
                        "gameId"
                    ].nunique(),

                "states":
                    len(group),

                "mean_prediction":
                    predicted,

                "observed_home_win_rate":
                    observed,

                "calibration_error":
                    observed
                    - predicted,

                "absolute_calibration_error":
                    abs(
                        observed
                        - predicted
                    ),
            }
        )

    return pd.DataFrame(rows)


def build_monthly_metrics(df):
    df = df.copy()

    df["gameDate"] = pd.to_datetime(
        df["gameDate"]
    )

    df["month"] = (
        df["gameDate"]
        .dt
        .to_period("M")
        .astype(str)
    )

    rows = []

    for month, group in df.groupby(
        "month",
        sort=True,
    ):
        state_metrics = calculate_metrics(
            group
        )

        balanced_metrics = calculate_metrics(
            group,
            weights=game_balanced_weights(
                group
            ),
        )

        rows.append(
            {
                "month": month,
                "weighting": "state",
                **state_metrics,
            }
        )

        rows.append(
            {
                "month": month,
                "weighting":
                    "game_balanced",
                **balanced_metrics,
            }
        )

    return pd.DataFrame(rows)


def build_season_half_metrics(df):
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

    game_table["gameDate"] = (
        pd.to_datetime(
            game_table["gameDate"]
        )
    )

    game_table = (
        game_table
        .sort_values(
            [
                "gameDate",
                "gameId",
            ],
            kind="mergesort",
        )
        .reset_index(drop=True)
    )

    midpoint = len(
        game_table
    ) // 2

    game_table[
        "seasonHalf"
    ] = "Second half"

    game_table.loc[
        : midpoint - 1,
        "seasonHalf",
    ] = "First half"

    merged = df.merge(
        game_table[
            [
                "gameId",
                "seasonHalf",
            ]
        ],
        on="gameId",
        how="left",
        validate="many_to_one",
    )

    rows = []

    for half in [
        "First half",
        "Second half",
    ]:
        group = merged[
            merged["seasonHalf"]
            == half
        ]

        state_metrics = calculate_metrics(
            group
        )

        balanced_metrics = calculate_metrics(
            group,
            weights=game_balanced_weights(
                group
            ),
        )

        rows.append(
            {
                "seasonHalf": half,
                "weighting": "state",
                **state_metrics,
            }
        )

        rows.append(
            {
                "seasonHalf": half,
                "weighting":
                    "game_balanced",
                **balanced_metrics,
            }
        )

    return pd.DataFrame(rows)


def print_metric_table(
    title,
    df,
    group_column,
):
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)

    columns = [
        group_column,
        "weighting",
        "games",
        "states",
        "accuracy",
        "log_loss",
        "brier",
        "auc",
        "ece",
    ]

    print(
        df[columns].to_string(
            index=False,
            float_format=lambda x:
                f"{x:.4f}",
        )
    )

def build_month_phase_metrics(df):
    df = df.copy()

    df["gameDate"] = pd.to_datetime(
        df["gameDate"]
    )

    df["month"] = (
        df["gameDate"]
        .dt
        .to_period("M")
        .astype(str)
    )

    rows = []

    for (month, phase), group in df.groupby(
        [
            "month",
            "gamePhase",
        ],
        observed=True,
        sort=True,
    ):
        metrics = calculate_metrics(
            group
        )

        rows.append(
            {
                "month":
                    month,

                "phase":
                    str(phase),

                **metrics,
            }
        )

    return pd.DataFrame(
        rows
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Analyze frozen V7 temporal "
            "generalization behavior."
        )
    )

    parser.add_argument(
        "--season",
        default="2025-26",
    )

    args = parser.parse_args()

    predictions_path = (
        RESULTS_DIR
        / (
            f"v7_{args.season}"
            "_predictions.csv"
        )
    )

    if not predictions_path.exists():
        raise FileNotFoundError(
            f"Missing predictions file: "
            f"{predictions_path}\n"
            "Run evaluate_frozen_v7.py first."
        )

    df = pd.read_csv(
        predictions_path
    )

    required_columns = {
        "gameId",
        "gameDate",
        "elapsedGameTime",
        "homeWin",
        "winProbability",
    }

    missing = (
        required_columns
        - set(df.columns)
    )

    if missing:
        raise ValueError(
            "Prediction file is missing "
            f"columns: {sorted(missing)}\n"
            f"Available columns: "
            f"{df.columns.tolist()}"
        )

    print(
        "Courtvision V7 "
        "Temporal Diagnostics"
    )

    print(
        "Season:",
        args.season,
    )

    print(
        "Games:",
        df["gameId"].nunique(),
    )

    print(
        "States:",
        len(df),
    )

    df = add_game_phase(
        df
    )

    phase_df = (
        build_phase_metrics(
            df
        )
    )

    calibration_df = (
        build_calibration_bins(
            df
        )
    )

    monthly_df = (
        build_monthly_metrics(
            df
        )
    )

    half_df = (
        build_season_half_metrics(
            df
        )
    )

    phase_path = (
        RESULTS_DIR
        / (
            f"v7_{args.season}"
            "_phase_metrics.csv"
        )
    )

    calibration_path = (
        RESULTS_DIR
        / (
            f"v7_{args.season}"
            "_calibration_bins.csv"
        )
    )

    monthly_path = (
        RESULTS_DIR
        / (
            f"v7_{args.season}"
            "_monthly_metrics.csv"
        )
    )

    half_path = (
        RESULTS_DIR
        / (
            f"v7_{args.season}"
            "_season_half_metrics.csv"
        )
    )

    phase_df.to_csv(
        phase_path,
        index=False,
    )

    calibration_df.to_csv(
        calibration_path,
        index=False,
    )

    monthly_df.to_csv(
        monthly_path,
        index=False,
    )

    half_df.to_csv(
        half_path,
        index=False,
    )

    print_metric_table(
        "Performance by game phase",
        phase_df,
        "phase",
    )

    print()
    print("=" * 80)
    print(
        "Calibration by "
        "prediction bin"
    )
    print("=" * 80)

    print(
        calibration_df.to_string(
            index=False,
            float_format=lambda x:
                f"{x:.4f}",
        )
    )

    print_metric_table(
        "Performance by month",
        monthly_df,
        "month",
    )

    print_metric_table(
        "First half vs second half",
        half_df,
        "seasonHalf",
    )

    print()
    print("Saved:")
    print(" ", phase_path)
    print(" ", calibration_path)
    print(" ", monthly_path)
    print(" ", half_path)

    month_phase_df = (
        build_month_phase_metrics(
            df
        )
    )

    month_phase_path = (
        RESULTS_DIR
        / (
            f"v7_{args.season}"
            "_month_phase_metrics.csv"
        )
    )

    month_phase_df.to_csv(
        month_phase_path,
        index=False,
    )

    print()
    print("=" * 80)
    print("Performance by month and game phase")
    print("=" * 80)

    print(
        month_phase_df[
            [
                "month",
                "phase",
                "games",
                "states",
                "accuracy",
                "log_loss",
                "brier",
                "auc",
                "ece",
            ]
        ].to_string(
            index=False,
            float_format=lambda x:
                f"{x:.4f}",
        )
    )

    print(
        " ",
        month_phase_path,
    )


if __name__ == "__main__":
    main()