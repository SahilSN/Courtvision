from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from player_rating_dataset import (
    PLAYER_INTELLIGENCE_DIR,
    validate_player_game_dataset,
)


REQUIRED_COLUMNS = {
    "season",
    "gameDate",
    "gameId",
    "personId",
    "playerName",
    "teamTricode",
    "minutes",
    "possessions",
    "netWPA",
    "absoluteWPA",
}

CANDIDATE_COLUMNS = [
    "cumulativeNetWPA",
    "netWPAper36",
    "netWPAper100Possessions",
    "shrunkNetWPAper36",
    "shrunkNetWPAper100Possessions",
]


def validate_source(dataset):
    validate_player_game_dataset(dataset)

    missing = REQUIRED_COLUMNS - set(dataset.columns)
    if missing:
        raise ValueError(
            "Candidate comparison source is missing columns: "
            f"{sorted(missing)}"
        )

    if dataset["possessions"].isna().any():
        raise ValueError(
            "Possessions are required for candidate comparison."
        )

    return True


def safe_divide(
    numerator,
    denominator,
):
    denominator = pd.to_numeric(
        denominator,
        errors="coerce",
    )

    return np.where(
        denominator > 0,
        numerator / denominator,
        np.nan,
    )


def build_candidate_table(
    dataset,
    prior_games=5.0,
):
    if prior_games <= 0:
        raise ValueError("prior_games must be positive.")

    validate_source(dataset)
    source = dataset.copy()
    source["gameDate"] = pd.to_datetime(
        source["gameDate"],
        errors="raise",
    )
    source = source.sort_values(
        [
            "gameDate",
            "gameId",
            "personId",
        ],
        kind="mergesort",
    )

    population_minutes = float(source["minutes"].sum())
    population_possessions = float(source["possessions"].sum())
    population_wpa = float(source["netWPA"].sum())

    if population_possessions <= 0:
        raise ValueError(
            "Candidate comparison requires positive possessions."
        )

    population_wpa_per_minute = population_wpa / population_minutes
    population_wpa_per_possession = (
        population_wpa / population_possessions
    )

    median_minutes = float(source["minutes"].median())
    positive_possessions = source.loc[
        source["possessions"] > 0,
        "possessions",
    ]
    median_possessions = float(positive_possessions.median())
    prior_minutes = prior_games * median_minutes
    prior_possessions = prior_games * median_possessions

    grouped = source.groupby(
        "personId",
        sort=True,
    )
    players = grouped.agg(
        playerName=("playerName", "last"),
        currentTeam=("teamTricode", "last"),
        games=("gameId", "nunique"),
        minutes=("minutes", "sum"),
        possessions=("possessions", "sum"),
        cumulativeNetWPA=("netWPA", "sum"),
        cumulativeAbsoluteWPA=("absoluteWPA", "sum"),
        bestGameNetWPA=("netWPA", "max"),
        worstGameNetWPA=("netWPA", "min"),
    ).reset_index()

    teams = grouped["teamTricode"].agg(
        lambda values: "/".join(
            dict.fromkeys(values.astype(str))
        )
    )
    players["teams"] = players["personId"].map(teams)

    players["netWPAper36"] = safe_divide(
        players["cumulativeNetWPA"] * 36.0,
        players["minutes"],
    )
    players["netWPAper100Possessions"] = safe_divide(
        players["cumulativeNetWPA"] * 100.0,
        players["possessions"],
    )

    players["minuteReliability"] = safe_divide(
        players["minutes"],
        players["minutes"] + prior_minutes,
    )
    players["possessionReliability"] = safe_divide(
        players["possessions"],
        players["possessions"] + prior_possessions,
    )
    players["shrunkNetWPAper36"] = (
        (
            players["cumulativeNetWPA"]
            + prior_minutes * population_wpa_per_minute
        )
        / (players["minutes"] + prior_minutes)
        * 36.0
    )
    players["shrunkNetWPAper100Possessions"] = (
        (
            players["cumulativeNetWPA"]
            + prior_possessions * population_wpa_per_possession
        )
        / (players["possessions"] + prior_possessions)
        * 100.0
    )
    players["shrunkAboveAveragePer36"] = (
        players["shrunkNetWPAper36"]
        - population_wpa_per_minute * 36.0
    )
    players["largestGameShare"] = safe_divide(
        players[
            [
                "bestGameNetWPA",
                "worstGameNetWPA",
            ]
        ].abs().max(axis=1),
        players["cumulativeAbsoluteWPA"],
    )

    for candidate in CANDIDATE_COLUMNS:
        players[f"{candidate}Rank"] = players[candidate].rank(
            method="min",
            ascending=False,
        ).astype("Int64")

    players.attrs["populationNetWPAper36"] = (
        population_wpa_per_minute * 36.0
    )
    players.attrs["populationNetWPAper100Possessions"] = (
        population_wpa_per_possession * 100.0
    )
    players.attrs["priorMinutes"] = prior_minutes
    players.attrs["priorPossessions"] = prior_possessions

    return players.sort_values(
        [
            "shrunkNetWPAper36Rank",
            "personId",
        ],
        kind="mergesort",
    ).reset_index(drop=True)


def spearman_correlation(
    left,
    right,
):
    valid = pd.DataFrame(
        {
            "left": left,
            "right": right,
        }
    ).dropna()

    if len(valid) < 2:
        return np.nan

    return valid["left"].rank().corr(
        valid["right"].rank()
    )


def build_candidate_diagnostics(
    players,
    top_n=10,
):
    rows = []

    for candidate in CANDIDATE_COLUMNS:
        ranked = players.sort_values(
            [
                candidate,
                "personId",
            ],
            ascending=[
                False,
                True,
            ],
            kind="mergesort",
        )
        leaders = ranked.head(top_n)
        rows.append(
            {
                "candidate": candidate,
                "players": int(ranked[candidate].notna().sum()),
                "minutesRankCorrelation": spearman_correlation(
                    ranked[candidate],
                    ranked["minutes"],
                ),
                "gamesRankCorrelation": spearman_correlation(
                    ranked[candidate],
                    ranked["games"],
                ),
                "topNMeanGames": float(leaders["games"].mean()),
                "topNPlayersWithOneGame": int(
                    leaders["games"].eq(1).sum()
                ),
                "topNMeanLargestGameShare": float(
                    leaders["largestGameShare"].mean()
                ),
            }
        )

    return pd.DataFrame(rows)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Compare opportunity normalization and empirical shrinkage "
            "candidates for Player Courtvision Rating."
        )
    )
    parser.add_argument(
        "--season",
        required=True,
    )
    parser.add_argument(
        "--input",
        type=Path,
    )
    parser.add_argument(
        "--prior-games",
        type=float,
        default=5.0,
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=10,
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.top_n <= 0:
        raise ValueError("top_n must be positive.")

    input_path = args.input or (
        PLAYER_INTELLIGENCE_DIR
        / f"{args.season}_player_game_v1.csv"
    )
    dataset = pd.read_csv(
        input_path,
        dtype={
            "gameId": str,
        },
    )
    players = build_candidate_table(
        dataset,
        prior_games=args.prior_games,
    )
    diagnostics = build_candidate_diagnostics(
        players,
        top_n=args.top_n,
    )

    player_output = (
        PLAYER_INTELLIGENCE_DIR
        / f"{args.season}_rating_candidates_v1.csv"
    )
    diagnostics_output = (
        PLAYER_INTELLIGENCE_DIR
        / f"{args.season}_rating_candidate_diagnostics_v1.csv"
    )
    player_output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    players.to_csv(
        player_output,
        index=False,
    )
    diagnostics.to_csv(
        diagnostics_output,
        index=False,
    )

    print("Player Courtvision Rating candidate comparison")
    print(f"season: {args.season}")
    print(f"player appearances: {len(dataset)}")
    print(f"players: {len(players)}")
    print(f"prior games: {args.prior_games:g}")
    print(
        "population net WPA per 36: "
        f"{players.attrs['populationNetWPAper36']:.4f}"
    )
    print(diagnostics.to_string(index=False))
    print("shrunk per-36 leaders")
    print(
        players[
            [
                "playerName",
                "currentTeam",
                "games",
                "minutes",
                "cumulativeNetWPA",
                "netWPAper36",
                "shrunkNetWPAper36",
                "minuteReliability",
            ]
        ]
        .head(args.top_n)
        .to_string(index=False)
    )
    print(f"saved: {player_output}")
    print(f"saved: {diagnostics_output}")


if __name__ == "__main__":
    main()
