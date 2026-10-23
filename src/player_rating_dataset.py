from __future__ import annotations

import argparse
import pickle
import re
from pathlib import Path

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT_DIR / "results"
WPA_DIR = RESULTS_DIR
BOX_CACHE_DIR = ROOT_DIR / "data" / "cache" / "box_score" / "v1"
CATALOG_DIR = ROOT_DIR / "data" / "cache" / "game_catalog"
PLAYER_INTELLIGENCE_DIR = RESULTS_DIR / "player_intelligence"


OUTPUT_COLUMNS = [
    "season",
    "gameDate",
    "gameId",
    "personId",
    "playerName",
    "teamTricode",
    "opponentTricode",
    "isHome",
    "teamWin",
    "starter",
    "minutes",
    "possessions",
    "attributedEvents",
    "netWPA",
    "positiveWPA",
    "negativeWPA",
    "absoluteWPA",
    "maxPositiveEvent",
    "maxNegativeEvent",
]


WPA_COLUMNS = [
    "events",
    "netWPA",
    "positiveWPA",
    "negativeWPA",
    "absoluteWPA",
    "maxPositiveEvent",
    "maxNegativeEvent",
]


def normalize_game_id(value):
    return str(value).zfill(10)


def parse_minutes(value):
    """Convert NBA minute strings to decimal minutes."""

    if value is None or pd.isna(value):
        return 0.0

    text = str(value).strip()

    if not text:
        return 0.0

    iso_match = re.fullmatch(
        r"PT(?:(\d+)M)?(\d+(?:\.\d+)?)S",
        text,
    )

    if iso_match is not None:
        return (
            float(iso_match.group(1) or 0)
            + float(iso_match.group(2)) / 60.0
        )

    clock_match = re.fullmatch(
        r"(\d+):(\d+(?:\.\d+)?)",
        text,
    )

    if clock_match is not None:
        return (
            float(clock_match.group(1))
            + float(clock_match.group(2)) / 60.0
        )

    try:
        return float(text)
    except ValueError as error:
        raise ValueError(
            f"Unexpected minutes value: {value!r}"
        ) from error


def load_game_catalog(
    season,
    catalog_dir=CATALOG_DIR,
):
    path = (
        Path(catalog_dir)
        / f"leaguegamelog_{season}_regular_season.csv"
    )

    if not path.exists():
        raise FileNotFoundError(
            f"Missing regular-season game catalog: {path}"
        )

    catalog = pd.read_csv(
        path,
        dtype={
            "GAME_ID": str,
        },
    )

    required = {
        "GAME_ID",
        "GAME_DATE",
        "TEAM_ABBREVIATION",
        "MATCHUP",
        "WL",
    }

    missing = required - set(catalog.columns)
    if missing:
        raise ValueError(
            "Game catalog is missing columns: "
            f"{sorted(missing)}"
        )

    catalog = catalog.copy()
    catalog["gameId"] = catalog["GAME_ID"].map(
        normalize_game_id
    )
    catalog["gameDate"] = pd.to_datetime(
        catalog["GAME_DATE"],
        errors="raise",
    ).dt.strftime("%Y-%m-%d")
    catalog["teamTricode"] = catalog[
        "TEAM_ABBREVIATION"
    ].astype(str)
    catalog["isHome"] = catalog["MATCHUP"].str.contains(
        "vs.",
        regex=False,
        na=False,
    ).astype(int)
    catalog["teamWin"] = catalog["WL"].eq("W").astype(int)

    opponents = (
        catalog[
            [
                "gameId",
                "teamTricode",
            ]
        ]
        .merge(
            catalog[
                [
                    "gameId",
                    "teamTricode",
                ]
            ],
            on="gameId",
            suffixes=("", "Opponent"),
        )
    )
    opponents = opponents.loc[
        opponents["teamTricode"]
        != opponents["teamTricodeOpponent"]
    ]

    team_games = catalog[
        [
            "gameId",
            "gameDate",
            "teamTricode",
            "isHome",
            "teamWin",
        ]
    ].merge(
        opponents.rename(
            columns={
                "teamTricodeOpponent": "opponentTricode",
            }
        ),
        on=[
            "gameId",
            "teamTricode",
        ],
        how="left",
        validate="one_to_one",
    )

    if team_games["opponentTricode"].isna().any():
        raise ValueError(
            "Could not resolve every catalog opponent."
        )

    team_games.insert(
        0,
        "season",
        season,
    )

    return team_games


def load_cached_box_players(
    game_id,
    box_cache_dir=BOX_CACHE_DIR,
):
    path = (
        Path(box_cache_dir)
        / f"{normalize_game_id(game_id)}.pkl"
    )

    if not path.exists():
        return None

    with path.open("rb") as cache_file:
        payload = pickle.load(cache_file)

    box_score = payload.get(
        "box_score",
        payload,
    )
    players = box_score.get("players")

    if not isinstance(players, pd.DataFrame):
        raise ValueError(
            f"Invalid cached player box score: {path}"
        )

    return players.copy()


def load_wpa_summary(
    game_id,
    wpa_dir=WPA_DIR,
):
    path = (
        Path(wpa_dir)
        / f"player_wpa_v3_{normalize_game_id(game_id)}_summary.csv"
    )

    if not path.exists():
        return None

    return pd.read_csv(path)


def build_player_game_rows(
    season,
    game_id,
    team_games,
    box_players,
    wpa_summary,
):
    required_box_columns = {
        "personId",
        "fullName",
        "teamTricode",
        "minutes",
        "starter",
    }
    missing_box = required_box_columns - set(box_players.columns)
    if missing_box:
        raise ValueError(
            "Player box score is missing columns: "
            f"{sorted(missing_box)}"
        )

    players = box_players.copy()
    players["gameId"] = normalize_game_id(game_id)
    players["minutes"] = players["minutes"].map(
        parse_minutes
    )
    players = players.loc[
        players["minutes"] > 0.0
    ].copy()
    players["personId"] = pd.to_numeric(
        players["personId"],
        errors="raise",
    ).astype(int)
    players["playerName"] = players["fullName"].astype(str)

    if "possessions" not in players.columns:
        players["possessions"] = pd.NA

    context = team_games.loc[
        team_games["gameId"] == normalize_game_id(game_id)
    ].copy()

    players = players.merge(
        context,
        on=[
            "gameId",
            "teamTricode",
        ],
        how="left",
        validate="many_to_one",
    )

    if players["opponentTricode"].isna().any():
        raise ValueError(
            f"Missing team context for game {game_id}."
        )

    impact = wpa_summary.copy()
    impact["personId"] = pd.to_numeric(
        impact["personId"],
        errors="raise",
    ).astype(int)
    impact = impact[
        [
            "personId",
            "teamTricode",
            *WPA_COLUMNS,
        ]
    ].rename(
        columns={
            "events": "attributedEvents",
        }
    )

    participant_keys = players[
        [
            "personId",
            "teamTricode",
        ]
    ]

    unmatched_impact = impact.merge(
        participant_keys,
        on=[
            "personId",
            "teamTricode",
        ],
        how="left",
        indicator=True,
        validate="one_to_one",
    )

    unmatched_impact = unmatched_impact.loc[
        unmatched_impact["_merge"] == "left_only"
    ]

    if not unmatched_impact.empty:
        raise ValueError(
            "WPA attribution rows are missing from positive-minute "
            f"box-score participants for game {game_id}: "
            f"{unmatched_impact['personId'].tolist()}"
        )

    players = players.merge(
        impact,
        on=[
            "personId",
            "teamTricode",
        ],
        how="left",
        validate="one_to_one",
    )

    players["attributedEvents"] = players[
        "attributedEvents"
    ].fillna(0).astype(int)

    for column in WPA_COLUMNS[1:]:
        players[column] = pd.to_numeric(
            players[column],
            errors="coerce",
        ).fillna(0.0)

    source_events = int(
        impact[
            "attributedEvents"
        ].sum()
    )
    joined_events = int(
        players[
            "attributedEvents"
        ].sum()
    )

    if source_events != joined_events:
        raise ValueError(
            f"Attributed event total changed while joining game {game_id}."
        )

    for column in WPA_COLUMNS[1:]:
        difference = abs(
            float(impact[column].sum())
            - float(players[column].sum())
        )

        if difference > 1e-9:
            raise ValueError(
                f"{column} total changed while joining game {game_id}."
            )

    players["season"] = season

    return players[OUTPUT_COLUMNS]


def validate_player_game_dataset(dataset):
    missing = set(OUTPUT_COLUMNS) - set(dataset.columns)
    if missing:
        raise ValueError(
            "Player-game dataset is missing columns: "
            f"{sorted(missing)}"
        )

    if dataset.empty:
        raise ValueError(
            "Player-game dataset is empty."
        )

    if dataset.duplicated(
        subset=[
            "season",
            "gameId",
            "personId",
        ]
    ).any():
        raise ValueError(
            "Duplicate player-game rows found."
        )

    if (dataset["minutes"] <= 0.0).any():
        raise ValueError(
            "Player-game dataset contains non-participants."
        )

    if not dataset["isHome"].isin([0, 1]).all():
        raise ValueError("isHome must contain only 0/1.")

    if not dataset["teamWin"].isin([0, 1]).all():
        raise ValueError("teamWin must contain only 0/1.")

    if (
        dataset["teamTricode"]
        == dataset["opponentTricode"]
    ).any():
        raise ValueError(
            "A player cannot have their own team as opponent."
        )

    return True


def build_player_game_dataset(
    season,
    wpa_dir=WPA_DIR,
    box_cache_dir=BOX_CACHE_DIR,
    catalog_dir=CATALOG_DIR,
):
    team_games = load_game_catalog(
        season,
        catalog_dir=catalog_dir,
    )

    game_ids = sorted(
        team_games["gameId"].unique()
    )
    rows = []
    missing_wpa = []
    missing_box = []

    for game_id in game_ids:
        wpa_summary = load_wpa_summary(
            game_id,
            wpa_dir=wpa_dir,
        )
        if wpa_summary is None:
            missing_wpa.append(game_id)
            continue

        box_players = load_cached_box_players(
            game_id,
            box_cache_dir=box_cache_dir,
        )
        if box_players is None:
            missing_box.append(game_id)
            continue

        rows.append(
            build_player_game_rows(
                season=season,
                game_id=game_id,
                team_games=team_games,
                box_players=box_players,
                wpa_summary=wpa_summary,
            )
        )

    if not rows:
        raise ValueError(
            f"No joined player-game rows are available for {season}."
        )

    dataset = pd.concat(
        rows,
        ignore_index=True,
    ).sort_values(
        [
            "gameDate",
            "gameId",
            "teamTricode",
            "personId",
        ],
        kind="mergesort",
    ).reset_index(drop=True)

    validate_player_game_dataset(
        dataset
    )

    diagnostics = {
        "season": season,
        "catalog_games": len(game_ids),
        "joined_games": int(dataset["gameId"].nunique()),
        "player_appearances": len(dataset),
        "players": int(dataset["personId"].nunique()),
        "zero_event_appearances": int(
            dataset["attributedEvents"].eq(0).sum()
        ),
        "missing_wpa_games": missing_wpa,
        "missing_box_games": missing_box,
    }

    return dataset, diagnostics


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Build the Player Courtvision Rating v1 "
            "player-game dataset from frozen WPA v3 and "
            "cached box-score participation."
        )
    )
    parser.add_argument(
        "--season",
        required=True,
    )
    parser.add_argument(
        "--output",
        type=Path,
    )
    return parser.parse_args()


def main():
    args = parse_args()
    dataset, diagnostics = build_player_game_dataset(
        args.season
    )

    output = args.output or (
        PLAYER_INTELLIGENCE_DIR
        / f"{args.season}_player_game_v1.csv"
    )
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    dataset.to_csv(
        output,
        index=False,
    )

    print("Player Courtvision Rating dataset")
    for key, value in diagnostics.items():
        if key.startswith("missing_"):
            print(f"{key}: {len(value)}")
        else:
            print(f"{key}: {value}")
    print(f"saved: {output}")


if __name__ == "__main__":
    main()

