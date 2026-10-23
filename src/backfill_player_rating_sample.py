from __future__ import annotations

import argparse
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd

from box_score import fetch_box_score
from player_impact import (
    analyze_player_impact,
    load_model,
    load_season_data,
    normalize_game_id,
)
from player_rating_dataset import (
    PLAYER_INTELLIGENCE_DIR,
    build_player_game_dataset,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
TRAINING_DIR = ROOT_DIR / "data" / "training"
RESULTS_DIR = ROOT_DIR / "results"
BOX_CACHE_DIR = ROOT_DIR / "data" / "cache" / "box_score" / "v1"

WPA_SUFFIXES = (
    "summary.csv",
    "events.csv",
    "sequences.csv",
)


def load_training_games(
    season,
    training_dir=TRAINING_DIR,
):
    path = (
        Path(training_dir)
        / f"{season}_training_v4_base.csv"
    )

    if not path.exists():
        raise FileNotFoundError(
            f"Missing season training dataset: {path}"
        )

    games = pd.read_csv(
        path,
        usecols=[
            "gameId",
            "gameDate",
        ],
        dtype={
            "gameId": str,
        },
    )
    games["gameId"] = games["gameId"].map(
        normalize_game_id
    )
    games["gameDate"] = pd.to_datetime(
        games["gameDate"],
        errors="raise",
    )

    return (
        games
        .drop_duplicates(
            subset=[
                "gameId",
            ]
        )
        .sort_values(
            [
                "gameDate",
                "gameId",
            ],
            kind="mergesort",
        )
        .reset_index(drop=True)
    )


def select_evenly_spaced_games(
    games,
    sample_size,
):
    if sample_size <= 0:
        raise ValueError("sample_size must be positive.")

    if sample_size >= len(games):
        return games.copy().reset_index(drop=True)

    indices = np.linspace(
        0,
        len(games) - 1,
        sample_size,
        dtype=int,
    )

    return games.iloc[indices].reset_index(drop=True)


def wpa_paths(
    game_id,
    results_dir=RESULTS_DIR,
):
    normalized_id = normalize_game_id(game_id)

    return tuple(
        Path(results_dir)
        / f"player_wpa_v3_{normalized_id}_{suffix}"
        for suffix in WPA_SUFFIXES
    )


def wpa_is_complete(
    game_id,
    results_dir=RESULTS_DIR,
):
    return all(
        path.exists()
        for path in wpa_paths(
            game_id,
            results_dir=results_dir,
        )
    )


def box_cache_path(
    game_id,
    box_cache_dir=BOX_CACHE_DIR,
):
    return (
        Path(box_cache_dir)
        / f"{normalize_game_id(game_id)}.pkl"
    )


def save_box_score_cache(
    game_id,
    box_score,
    box_cache_dir=BOX_CACHE_DIR,
):
    path = box_cache_path(
        game_id,
        box_cache_dir=box_cache_dir,
    )
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    temporary_path = path.with_suffix(".pkl.tmp")

    with temporary_path.open("wb") as cache_file:
        pickle.dump(
            {
                "cache_version": "v1",
                "game_id": normalize_game_id(game_id),
                "box_score": box_score,
            },
            cache_file,
            protocol=pickle.HIGHEST_PROTOCOL,
        )

    temporary_path.replace(path)
    return path


def fetch_and_cache_box_score(
    game_id,
    retries=3,
    retry_delay=2.0,
    fetcher=fetch_box_score,
    box_cache_dir=BOX_CACHE_DIR,
):
    if retries <= 0:
        raise ValueError("retries must be positive.")

    if retry_delay < 0:
        raise ValueError("retry_delay cannot be negative.")

    last_error = None

    for attempt in range(1, retries + 1):
        try:
            box_score = fetcher(
                normalize_game_id(game_id)
            )
            return save_box_score_cache(
                game_id,
                box_score,
                box_cache_dir=box_cache_dir,
            )
        except Exception as error:
            last_error = error

            if attempt < retries:
                time.sleep(retry_delay)

    raise RuntimeError(
        f"Box score failed after {retries} attempts: {last_error}"
    ) from last_error


def build_work_plan(
    selected_games,
    force=False,
    results_dir=RESULTS_DIR,
    box_cache_dir=BOX_CACHE_DIR,
):
    plan = []

    for row in selected_games.itertuples(index=False):
        game_id = normalize_game_id(row.gameId)
        needs_wpa = force or not wpa_is_complete(
            game_id,
            results_dir=results_dir,
        )
        needs_box = force or not box_cache_path(
            game_id,
            box_cache_dir=box_cache_dir,
        ).exists()

        plan.append(
            {
                "gameId": game_id,
                "gameDate": row.gameDate,
                "needsWPA": needs_wpa,
                "needsBoxScore": needs_box,
            }
        )

    return pd.DataFrame(plan)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Build a deterministic, resumable historical sample for "
            "Player Courtvision Rating research."
        )
    )
    parser.add_argument(
        "--season",
        required=True,
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=50,
    )
    parser.add_argument(
        "--max-new-games",
        type=int,
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=2.0,
    )
    parser.add_argument(
        "--force",
        action="store_true",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.max_new_games is not None and args.max_new_games <= 0:
        raise ValueError("max_new_games must be positive.")

    games = load_training_games(args.season)
    selected = select_evenly_spaced_games(
        games,
        args.sample_size,
    )
    plan = build_work_plan(
        selected,
        force=args.force,
    )
    pending = plan.loc[
        plan["needsWPA"]
        | plan["needsBoxScore"]
    ]

    print("Player Courtvision Rating sample backfill")
    print(f"season: {args.season}")
    print(f"season games: {len(games)}")
    print(f"selected games: {len(selected)}")
    print(f"complete games: {len(plan) - len(pending)}")
    print(f"pending games: {len(pending)}")

    if args.dry_run:
        for row in plan.itertuples(index=False):
            state = []
            if row.needsWPA:
                state.append("WPA")
            if row.needsBoxScore:
                state.append("box")
            print(
                row.gameId,
                row.gameDate.strftime("%Y-%m-%d"),
                ",".join(state) or "complete",
            )
        return

    limit = args.max_new_games or len(pending)
    work = pending.head(limit)
    failures = []
    season_df = None
    model = None
    scaler = None
    device = None

    if work["needsWPA"].any():
        print("loading frozen V7 artifacts...")
        season_df = load_season_data(args.season)
        model, scaler, device = load_model()

    for position, row in enumerate(
        work.itertuples(index=False),
        start=1,
    ):
        print(
            f"[{position}/{len(work)}] {row.gameId} "
            f"({row.gameDate.strftime('%Y-%m-%d')})"
        )

        if row.needsWPA:
            try:
                analyze_player_impact(
                    row.gameId,
                    args.season,
                    season_df=season_df,
                    model=model,
                    scaler=scaler,
                    device=device,
                )
            except Exception as error:
                failures.append(
                    {
                        "gameId": row.gameId,
                        "stage": "WPA",
                        "error": str(error),
                    }
                )
                print(f"  WPA failed: {error}")

        if row.needsBoxScore:
            try:
                path = fetch_and_cache_box_score(
                    row.gameId,
                    retries=args.retries,
                    retry_delay=args.retry_delay,
                )
                print(f"  box score cached: {path}")
            except Exception as error:
                failures.append(
                    {
                        "gameId": row.gameId,
                        "stage": "box score",
                        "error": str(error),
                    }
                )
                print(f"  box score failed: {error}")

    dataset, diagnostics = build_player_game_dataset(
        args.season
    )
    output = (
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

    print("dataset rebuilt")
    print(f"joined games: {diagnostics['joined_games']}")
    print(f"player appearances: {diagnostics['player_appearances']}")
    print(f"players: {diagnostics['players']}")
    print(f"failures: {len(failures)}")
    print(f"saved: {output}")

    if failures:
        print(pd.DataFrame(failures).to_string(index=False))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
