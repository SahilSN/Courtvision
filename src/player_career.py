"""Published player coverage and career summaries over covered regular-season games."""

from pathlib import Path

import pandas as pd

from player_rating_config import (
    RATING_POINTS_PER_REFERENCE,
    REFERENCE_NET_WPA_PER_36,
    REFERENCE_PRIOR_MINUTES,
)
from player_rating_dataset import PLAYER_INTELLIGENCE_DIR, validate_player_game_dataset
from season_config import CURRENT_SEASON


def season_coverage(season, games, team_history=None):
    processed = set(games["gameId"].astype(str).str.zfill(10))
    expected = (
        set(team_history["gameId"].astype(str).str.zfill(10))
        if team_history is not None else set()
    )
    # Current team/player publishers may finish at different times.
    if season == CURRENT_SEASON:
        expected |= processed
    elif expected and not processed.issubset(expected):
        raise ValueError(f"Player games are outside the {season} regular-season catalog.")
    return {
        "season": season,
        "processedGames": len(processed),
        "expectedGames": len(expected) if expected else None,
        "coverageStatus": (
            "In progress" if season == CURRENT_SEASON else
            "Complete" if expected and processed == expected else
            "Partial" if expected else "Unknown"
        ),
    }


def load_published_player_data(output_dir=PLAYER_INTELLIGENCE_DIR):
    output_dir = Path(output_dir)
    summaries, appearances, coverage = [], [], []
    for path in sorted(output_dir.glob("*_player_ratings_v1.csv")):
        season = path.name.removesuffix("_player_ratings_v1.csv")
        games_path = output_dir / f"{season}_player_game_v1.csv"
        if not games_path.exists():
            continue
        games = pd.read_csv(games_path, dtype={"gameId": str})
        summary = pd.read_csv(path)
        validate_player_game_dataset(games)
        if not games["season"].eq(season).all() or not summary["season"].eq(season).all():
            raise ValueError(f"Published player data does not match {season}.")
        if summary["personId"].duplicated().any():
            raise ValueError(f"Duplicate player summaries in {season}.")
        history_path = output_dir.parent / "season_intelligence" / f"{season}_team_rating_games_v1.csv"
        team_history = pd.read_csv(history_path, dtype={"gameId": str}) if history_path.exists() else None
        coverage.append(season_coverage(season, games, team_history))
        summaries.append(summary)
        appearances.append(games)
    if not summaries:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    return (
        pd.concat(summaries, ignore_index=True),
        pd.concat(appearances, ignore_index=True),
        pd.DataFrame(coverage),
    )


def build_player_career(games, person_id):
    """Pool actual covered appearances, with one fixed prior across the whole span."""
    player = games.loc[games["personId"].eq(person_id)].copy()
    if player.empty:
        raise ValueError("No covered appearances for this player.")
    if player.duplicated(["season", "gameId", "personId"]).any():
        raise ValueError("Duplicate career player-game rows.")
    minutes = float(player["minutes"].sum())
    net_wpa = float(player["netWPA"].sum())
    posterior_per_36 = (
        net_wpa + REFERENCE_PRIOR_MINUTES * REFERENCE_NET_WPA_PER_36 / 36.0
    ) / (minutes + REFERENCE_PRIOR_MINUTES) * 36.0
    return {
        "seasons": int(player["season"].nunique()),
        "games": len(player),
        "minutes": minutes,
        "seasonNetWPA": net_wpa,
        "netWPAper36": net_wpa / minutes * 36.0 if minutes > 0 else 0.0,
        "coveredRating": round(100.0 + RATING_POINTS_PER_REFERENCE * (
            posterior_per_36 / REFERENCE_NET_WPA_PER_36 - 1.0
        ), 1),
    }
