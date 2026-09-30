from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


ROOT_DIR = (
    Path(__file__)
    .resolve()
    .parents[1]
)

TEAM_RATING_DIR = (
    ROOT_DIR
    / "results"
    / "team_rating"
)

SEASON_INTELLIGENCE_DIR = (
    ROOT_DIR
    / "results"
    / "season_intelligence"
)

INITIAL_RATING = 1500.0


# ============================================================
# Input
# ============================================================

def load_rating_artifacts(
    season,
):
    history_path = (
        TEAM_RATING_DIR
        / (
            f"{season}_"
            "courtvision_rating_history_v1.csv"
        )
    )

    ratings_path = (
        TEAM_RATING_DIR
        / (
            f"{season}_"
            "courtvision_rating_ratings_v1.csv"
        )
    )

    if not history_path.exists():
        raise FileNotFoundError(
            f"Missing rating history: {history_path}"
        )

    if not ratings_path.exists():
        raise FileNotFoundError(
            f"Missing final ratings: {ratings_path}"
        )

    history = pd.read_csv(
        history_path,
        dtype={
            "gameId": str,
        },
    )

    ratings = pd.read_csv(
        ratings_path,
    )

    return (
        history,
        ratings,
    )


# ============================================================
# Team game histories
# ============================================================

def build_team_game_history(
    history,
):
    home = pd.DataFrame(
        {
            "season":
                history[
                    "season"
                ],

            "gameDate":
                history[
                    "gameDate"
                ],

            "gameId":
                history[
                    "gameId"
                ],

            "team":
                history[
                    "homeTeam"
                ],

            "opponent":
                history[
                    "awayTeam"
                ],

            "isHome":
                1,

            "teamWin":
                history[
                    "homeWin"
                ].astype(
                    int
                ),

            "ratingBefore":
                history[
                    "homeRatingBefore"
                ],

            "ratingAfter":
                history[
                    "homeRatingAfter"
                ],

            "ratingChange":
                history[
                    "homeRatingChange"
                ],

            "opponentRatingBefore":
                history[
                    "awayRatingBefore"
                ],

            "pregameWinProbability":
                history[
                    "homeExpectedWinProb"
                ],

            "winnerMargin":
                history[
                    "winnerMargin"
                ],

            "signedMargin":
                np.where(
                    history[
                        "homeWin"
                    ].astype(
                        int
                    )
                    == 1,
                    history[
                        "winnerMargin"
                    ],
                    -history[
                        "winnerMargin"
                    ],
                ),

            "marginDominance":
                history[
                    "marginDominance"
                ],

            "dominanceMultiplier":
                history[
                    "dominanceMultiplier"
                ],
        }
    )

    away = pd.DataFrame(
        {
            "season":
                history[
                    "season"
                ],

            "gameDate":
                history[
                    "gameDate"
                ],

            "gameId":
                history[
                    "gameId"
                ],

            "team":
                history[
                    "awayTeam"
                ],

            "opponent":
                history[
                    "homeTeam"
                ],

            "isHome":
                0,

            "teamWin":
                (
                    1
                    - history[
                        "homeWin"
                    ].astype(
                        int
                    )
                ),

            "ratingBefore":
                history[
                    "awayRatingBefore"
                ],

            "ratingAfter":
                history[
                    "awayRatingAfter"
                ],

            "ratingChange":
                history[
                    "awayRatingChange"
                ],

            "opponentRatingBefore":
                history[
                    "homeRatingBefore"
                ],

            "pregameWinProbability":
                history[
                    "awayExpectedWinProb"
                ],

            "winnerMargin":
                history[
                    "winnerMargin"
                ],

            "signedMargin":
                np.where(
                    history[
                        "homeWin"
                    ].astype(
                        int
                    )
                    == 0,
                    history[
                        "winnerMargin"
                    ],
                    -history[
                        "winnerMargin"
                    ],
                ),

            "marginDominance":
                history[
                    "marginDominance"
                ],

            "dominanceMultiplier":
                history[
                    "dominanceMultiplier"
                ],
        }
    )

    team_history = pd.concat(
        [
            home,
            away,
        ],
        ignore_index=True,
    )

    team_history[
        "_sortDate"
    ] = pd.to_datetime(
        team_history[
            "gameDate"
        ],
        errors="coerce",
    )

    if team_history[
        "_sortDate"
    ].isna().any():
        raise ValueError(
            "Invalid gameDate in rating history."
        )

    team_history = (
        team_history
        .sort_values(
            [
                "team",
                "_sortDate",
                "gameId",
            ],
            kind="mergesort",
        )
        .drop(
            columns=[
                "_sortDate",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    team_history[
        "teamGameNumber"
    ] = (
        team_history
        .groupby(
            "team"
        )
        .cumcount()
        + 1
    )

    return team_history


# ============================================================
# Summary metrics
# ============================================================

def recent_rating_change(
    team_games,
    window,
):
    recent = (
        team_games
        .tail(
            window
        )
    )

    if recent.empty:
        return 0.0

    return float(
        recent[
            "ratingChange"
        ].sum()
    )


def build_team_summary(
    team_history,
    ratings,
):
    rows = []

    ratings_by_team = (
        ratings
        .set_index(
            "team"
        )
    )

    for team, games in (
        team_history
        .groupby(
            "team",
            sort=True,
        )
    ):
        games = (
            games
            .sort_values(
                [
                    "teamGameNumber",
                ]
            )
            .reset_index(
                drop=True
            )
        )

        if team not in ratings_by_team.index:
            raise ValueError(
                f"{team} missing from final ratings."
            )

        final = (
            ratings_by_team
            .loc[
                team
            ]
        )

        wins = (
            games[
                games[
                    "teamWin"
                ]
                == 1
            ]
        )

        losses = (
            games[
                games[
                    "teamWin"
                ]
                == 0
            ]
        )

        current_rating = float(
            final[
                "currentRating"
            ]
        )

        rows.append(
            {
                "team":
                    team,

                "ratingRank":
                    int(
                        final[
                            "ratingRank"
                        ]
                    ),

                "gamesPlayed":
                    int(
                        len(
                            games
                        )
                    ),

                "wins":
                    int(
                        final[
                            "wins"
                        ]
                    ),

                "losses":
                    int(
                        final[
                            "losses"
                        ]
                    ),

                "currentRating":
                    current_rating,

                "peakRating":
                    float(
                        final[
                            "peakRating"
                        ]
                    ),

                "lowestRating":
                    float(
                        final[
                            "lowestRating"
                        ]
                    ),

                "seasonRatingChange":
                    float(
                        current_rating
                        - INITIAL_RATING
                    ),

                "last5RatingChange":
                    recent_rating_change(
                        games,
                        5,
                    ),

                "last10RatingChange":
                    recent_rating_change(
                        games,
                        10,
                    ),

                "largestSingleGameGain":
                    (
                        float(
                            wins[
                                "ratingChange"
                            ].max()
                        )
                        if not wins.empty
                        else np.nan
                    ),

                # Intentionally signed:
                # e.g. -28.4 means rating fell 28.4 points.
                "largestSingleGameLoss":
                    (
                        float(
                            losses[
                                "ratingChange"
                            ].min()
                        )
                        if not losses.empty
                        else np.nan
                    ),

                "averageWinGain":
                    (
                        float(
                            wins[
                                "ratingChange"
                            ].mean()
                        )
                        if not wins.empty
                        else np.nan
                    ),

                # Intentionally signed negative.
                "averageLossDrop":
                    (
                        float(
                            losses[
                                "ratingChange"
                            ].mean()
                        )
                        if not losses.empty
                        else np.nan
                    ),

                "lastGameDate":
                    games[
                        "gameDate"
                    ].iloc[
                        -1
                    ],
            }
        )

    summary = pd.DataFrame(
        rows
    )

    summary = (
        summary
        .sort_values(
            [
                "ratingRank",
                "team",
            ],
            kind="mergesort",
        )
        .reset_index(
            drop=True
        )
    )

    return summary


# ============================================================
# Validation
# ============================================================

def validate_team_summary(
    summary,
    team_history,
    ratings,
):
    if len(
        summary
    ) != 30:
        raise ValueError(
            f"Expected 30 teams, found {len(summary)}."
        )

    if summary[
        "team"
    ].duplicated().any():
        raise ValueError(
            "Duplicate team in season summary."
        )

    if set(
        summary[
            "team"
        ]
    ) != set(
        ratings[
            "team"
        ]
    ):
        raise ValueError(
            "Summary and final-rating team sets differ."
        )

    if not (
        summary[
            "gamesPlayed"
        ]
        == (
            summary[
                "wins"
            ]
            + summary[
                "losses"
            ]
        )
    ).all():
        raise ValueError(
            "wins + losses != gamesPlayed."
        )

    if not np.allclose(
        summary[
            "seasonRatingChange"
        ],
        (
            summary[
                "currentRating"
            ]
            - INITIAL_RATING
        ),
        atol=1e-9,
        rtol=0.0,
    ):
        raise ValueError(
            "Invalid seasonRatingChange."
        )

    # Winners must gain rating and losers must lose rating.
    if (
        team_history.loc[
            team_history[
                "teamWin"
            ]
            == 1,
            "ratingChange",
        ]
        <= 0
    ).any():
        raise ValueError(
            "Winning team received non-positive rating change."
        )

    if (
        team_history.loc[
            team_history[
                "teamWin"
            ]
            == 0,
            "ratingChange",
        ]
        >= 0
    ).any():
        raise ValueError(
            "Losing team received non-negative rating change."
        )

    if (
        summary[
            "largestSingleGameGain"
        ]
        <= 0
    ).any():
        raise ValueError(
            "largestSingleGameGain must be positive."
        )

    if (
        summary[
            "largestSingleGameLoss"
        ]
        >= 0
    ).any():
        raise ValueError(
            "largestSingleGameLoss must be negative."
        )

    if (
        summary[
            "averageWinGain"
        ]
        <= 0
    ).any():
        raise ValueError(
            "averageWinGain must be positive."
        )

    if (
        summary[
            "averageLossDrop"
        ]
        >= 0
    ).any():
        raise ValueError(
            "averageLossDrop must be negative."
        )

    # Final team-history state must match frozen final rating.
    final_from_history = (
        team_history
        .sort_values(
            [
                "team",
                "teamGameNumber",
            ]
        )
        .groupby(
            "team",
            as_index=False,
        )
        .tail(
            1
        )[
            [
                "team",
                "ratingAfter",
            ]
        ]
        .rename(
            columns={
                "ratingAfter":
                    "historyFinalRating",
            }
        )
    )

    check = (
        summary[
            [
                "team",
                "currentRating",
            ]
        ]
        .merge(
            final_from_history,
            on="team",
            how="left",
            validate="one_to_one",
        )
    )

    if not np.allclose(
        check[
            "currentRating"
        ],
        check[
            "historyFinalRating"
        ],
        atol=1e-8,
        rtol=0.0,
    ):
        raise ValueError(
            "Summary rating does not match final history state."
        )

    print(
        "✓ Team Season Intelligence validation passed."
    )


# ============================================================
# Build
# ============================================================

def build_season_team_summary(
    season,
):
    history, ratings = (
        load_rating_artifacts(
            season
        )
    )

    team_history = (
        build_team_game_history(
            history
        )
    )

    summary = (
        build_team_summary(
            team_history,
            ratings,
        )
    )

    validate_team_summary(
        summary,
        team_history,
        ratings,
    )

    SEASON_INTELLIGENCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    summary_path = (
        SEASON_INTELLIGENCE_DIR
        / (
            f"{season}_"
            "team_summary_v1.csv"
        )
    )

    team_history_path = (
        SEASON_INTELLIGENCE_DIR
        / (
            f"{season}_"
            "team_rating_games_v1.csv"
        )
    )

    summary.to_csv(
        summary_path,
        index=False,
    )

    team_history.to_csv(
        team_history_path,
        index=False,
    )

    return (
        summary,
        summary_path,
        team_history_path,
    )


# ============================================================
# CLI
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Courtvision Season Intelligence — "
            "Stage 4 team summaries."
        )
    )

    parser.add_argument(
        "--season",
        required=True,
    )

    return parser.parse_args()


def main():
    args = parse_args()

    summary, summary_path, history_path = (
        build_season_team_summary(
            args.season
        )
    )

    print()
    print(
        "Courtvision Season Intelligence — Stage 4"
    )

    print(
        f"Season: {args.season}"
    )

    print(
        f"Teams: {len(summary)}"
    )

    print()

    print(
        summary[
            [
                "ratingRank",
                "team",
                "wins",
                "losses",
                "currentRating",
                "seasonRatingChange",
                "last5RatingChange",
                "last10RatingChange",
            ]
        ]
        .head(
            15
        )
        .to_string(
            index=False
        )
    )

    print()
    print(
        f"Summary: {summary_path}"
    )

    print(
        f"Team-game history: {history_path}"
    )


if __name__ == "__main__":
    main()
