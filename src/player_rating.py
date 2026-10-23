from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from compare_player_rating_candidates import (
    build_candidate_table,
)
from player_rating_config import (
    LEADERBOARD_MIN_GAMES,
    QUALIFIED_MIN_GAMES,
    QUALIFIED_MIN_RELIABILITY,
    RATING_POINTS_PER_REFERENCE,
    REFERENCE_NET_WPA_PER_36,
    REFERENCE_PRIOR_MINUTES,
)
from player_rating_dataset import (
    PLAYER_INTELLIGENCE_DIR,
)


OUTPUT_COLUMNS = [
    "season",
    "personId",
    "playerName",
    "currentTeam",
    "teams",
    "games",
    "minutes",
    "possessions",
    "courtvisionRating",
    "courtvisionRank",
    "ratingStatus",
    "leaderboardEligible",
    "ratingReliability",
    "seasonNetWPA",
    "seasonValueRank",
    "netWPAper36",
    "shrunkNetWPAper36",
    "ratingAboveAverage",
    "bestGameNetWPA",
    "worstGameNetWPA",
]


def rating_status(
    games,
    reliability,
):
    if games < LEADERBOARD_MIN_GAMES:
        return "Limited"

    if (
        games < QUALIFIED_MIN_GAMES
        or reliability < QUALIFIED_MIN_RELIABILITY
    ):
        return "Provisional"

    return "Qualified"


def build_player_ratings(
    dataset,
):
    if dataset["season"].nunique() != 1:
        raise ValueError(
            "Player ratings require exactly one season."
        )

    season = str(dataset["season"].iloc[0])
    players = build_candidate_table(
        dataset,
        prior_games=5.0,
    ).copy()
    players["season"] = season
    players["ratingReliability"] = (
        players["minutes"]
        / (
            players["minutes"]
            + REFERENCE_PRIOR_MINUTES
        )
    )
    players["courtvisionRatingRaw"] = (
        100.0
        + RATING_POINTS_PER_REFERENCE
        * (
            players["fixedBaselineShrunkNetWPAper36"]
            / REFERENCE_NET_WPA_PER_36
            - 1.0
        )
    )
    players["courtvisionRating"] = players[
        "courtvisionRatingRaw"
    ].round(1)
    players["ratingAboveAverage"] = (
        players["courtvisionRating"] - 100.0
    ).round(1)
    players["seasonNetWPA"] = players[
        "cumulativeNetWPA"
    ]
    players["leaderboardEligible"] = players[
        "games"
    ].ge(LEADERBOARD_MIN_GAMES)
    players["ratingStatus"] = [
        rating_status(games, reliability)
        for games, reliability in zip(
            players["games"],
            players["ratingReliability"],
        )
    ]

    players["courtvisionRank"] = pd.Series(
        pd.NA,
        index=players.index,
        dtype="Int64",
    )
    players["seasonValueRank"] = pd.Series(
        pd.NA,
        index=players.index,
        dtype="Int64",
    )
    eligible = players["leaderboardEligible"]
    players.loc[
        eligible,
        "courtvisionRank",
    ] = players.loc[
        eligible,
        "courtvisionRatingRaw",
    ].rank(
        method="min",
        ascending=False,
    ).astype("Int64")
    players.loc[
        eligible,
        "seasonValueRank",
    ] = players.loc[
        eligible,
        "seasonNetWPA",
    ].rank(
        method="min",
        ascending=False,
    ).astype("Int64")

    result = players[OUTPUT_COLUMNS].sort_values(
        [
            "leaderboardEligible",
            "courtvisionRank",
            "courtvisionRating",
            "personId",
        ],
        ascending=[
            False,
            True,
            False,
            True,
        ],
        kind="mergesort",
        na_position="last",
    ).reset_index(drop=True)

    if result["personId"].duplicated().any():
        raise ValueError("Duplicate players found in rating output.")

    if not np.isfinite(result["courtvisionRating"]).all():
        raise ValueError("Player ratings contain non-finite values.")

    return result


def build_player_rating_history(dataset, person_id):
    """Reconstruct each post-game estimate using only appearances up to that game."""
    if dataset["season"].nunique() != 1:
        raise ValueError("Player history requires exactly one season.")

    history = dataset.loc[dataset["personId"].eq(person_id)].copy()
    history["gameDate"] = pd.to_datetime(history["gameDate"], errors="raise")
    history["gameId"] = history["gameId"].astype(str).str.zfill(10)
    history = history.sort_values(
        ["gameDate", "gameId"], kind="mergesort"
    ).reset_index(drop=True)
    if history["gameId"].duplicated().any():
        raise ValueError("Duplicate player appearances in rating history.")

    history["games"] = np.arange(1, len(history) + 1)
    history["cumulativeMinutes"] = history["minutes"].cumsum()
    history["seasonNetWPA"] = history["netWPA"].cumsum()
    history["ratingReliability"] = history["cumulativeMinutes"] / (
        history["cumulativeMinutes"] + REFERENCE_PRIOR_MINUTES
    )
    posterior_per_36 = (
        history["seasonNetWPA"]
        + REFERENCE_PRIOR_MINUTES * REFERENCE_NET_WPA_PER_36 / 36.0
    ) / (history["cumulativeMinutes"] + REFERENCE_PRIOR_MINUTES) * 36.0
    history["courtvisionRating"] = (
        100.0 + RATING_POINTS_PER_REFERENCE
        * (posterior_per_36 / REFERENCE_NET_WPA_PER_36 - 1.0)
    ).round(1)
    history["ratingStatus"] = [
        rating_status(games, reliability)
        for games, reliability in zip(history["games"], history["ratingReliability"])
    ]
    return history


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Build frozen Player Courtvision Rating v1 season summaries."
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
        "--output",
        type=Path,
    )
    return parser.parse_args()


def main():
    args = parse_args()
    input_path = args.input or (
        PLAYER_INTELLIGENCE_DIR
        / f"{args.season}_player_game_v1.csv"
    )
    output_path = args.output or (
        PLAYER_INTELLIGENCE_DIR
        / f"{args.season}_player_ratings_v1.csv"
    )
    dataset = pd.read_csv(
        input_path,
        dtype={
            "gameId": str,
        },
    )
    ratings = build_player_ratings(
        dataset
    )
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    ratings.to_csv(
        output_path,
        index=False,
    )

    print("Player Courtvision Rating v1")
    print(f"season: {args.season}")
    print(f"players: {len(ratings)}")
    print(
        "leaderboard eligible: "
        f"{int(ratings['leaderboardEligible'].sum())}"
    )
    print(
        ratings[
            [
                "courtvisionRank",
                "playerName",
                "currentTeam",
                "games",
                "courtvisionRating",
                "ratingStatus",
                "ratingReliability",
                "seasonNetWPA",
            ]
        ]
        .head(15)
        .to_string(index=False)
    )
    print(f"saved: {output_path}")


if __name__ == "__main__":
    main()
