"""Resumable full-season publication using frozen historical WPA and box participation."""

import argparse
import contextlib
import io
import fcntl
from pathlib import Path

import pandas as pd

from backfill_player_rating_sample import (
    box_cache_path, fetch_and_cache_box_score, load_training_games, wpa_is_complete,
)
from player_impact import analyze_player_impact, load_model, load_season_data
from player_rating import build_player_ratings
from compare_player_rating_candidates import validate_source
from player_rating_dataset import (
    PLAYER_INTELLIGENCE_DIR, build_player_game_rows, load_cached_box_players,
    load_game_catalog, load_wpa_summary, validate_player_game_dataset,
)
from update_live_season import atomic_write_csv
from update_player_intelligence import load_existing_player_games, player_game_path, player_rating_path


def backfill_season(season, max_new_games=None, cached_only=False,
                    output_dir=PLAYER_INTELLIGENCE_DIR, failure_limit=5):
    """Serialize writers and always flush successful appearances on interruption."""
    if failure_limit < 1:
        raise ValueError("failure_limit must be positive")
    runtime = Path(output_dir) / ".runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / "checkpoint.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _backfill_season(season, max_new_games, cached_only, output_dir, failure_limit)


def _backfill_season(season, max_new_games, cached_only, output_dir, failure_limit):
    team_games = load_game_catalog(season)
    all_games = load_training_games(season)
    expected = set(team_games["gameId"])
    if set(all_games["gameId"]) != expected:
        raise ValueError(f"Training coverage does not match the full {season} catalog.")
    existing = load_existing_player_games(season, output_dir=output_dir)
    done = set(existing["gameId"])
    if not done.issubset(expected):
        raise ValueError("Saved games are outside the regular-season catalog.")
    pending = all_games.loc[~all_games["gameId"].isin(done)]
    if cached_only:
        pending = pending.loc[pending["gameId"].map(
            lambda game_id: wpa_is_complete(game_id) and box_cache_path(game_id).exists()
        )]
    if max_new_games is not None:
        pending = pending.head(max_new_games)
    frames = [] if existing.empty else [existing]
    season_df = artifacts = None
    failures = []

    def publish():
        if not frames:
            return
        dataset = pd.concat(frames, ignore_index=True).sort_values(
            ["gameDate", "gameId", "personId"], kind="mergesort"
        )
        validate_player_game_dataset(dataset)
        ratings = build_player_ratings(dataset)
        atomic_write_csv(dataset, player_game_path(season, output_dir=output_dir))
        atomic_write_csv(ratings, player_rating_path(season, output_dir=output_dir))

    print(f"{season}: {len(done)}/{len(expected)} published; {len(pending)} selected", flush=True)
    consecutive_failures = 0
    try:
        for index, game in enumerate(pending.itertuples(index=False), 1):
            try:
                if not wpa_is_complete(game.gameId):
                    if season_df is None:
                        season_df, artifacts = load_season_data(season), load_model()
                    with contextlib.redirect_stdout(io.StringIO()):
                        analyze_player_impact(game.gameId, season, season_df=season_df,
                                             model=artifacts[0], scaler=artifacts[1], device=artifacts[2])
                had_cached_box = box_cache_path(game.gameId).exists()
                if not had_cached_box:
                    fetch_and_cache_box_score(game.gameId, retries=1)
                rows = build_player_game_rows(
                    season, game.gameId, team_games,
                    load_cached_box_players(game.gameId), load_wpa_summary(game.gameId),
                )
                if had_cached_box and rows["possessions"].isna().any():
                    # Cached partial box data must not poison a checkpoint or
                    # remain permanently unrepairable. Refresh once, then fail
                    # visibly if the provider still omits required data.
                    fetch_and_cache_box_score(game.gameId, retries=1)
                    rows = build_player_game_rows(
                        season, game.gameId, team_games,
                        load_cached_box_players(game.gameId), load_wpa_summary(game.gameId),
                    )
                validate_source(rows)
                frames.append(rows)
                done.add(game.gameId)
                consecutive_failures = 0
                print(f"{season} [{index}/{len(pending)}] {game.gameId}: OK ({len(done)}/{len(expected)})", flush=True)
            except Exception as error:
                failures.append({"gameId": game.gameId, "error": str(error)})
                consecutive_failures += 1
                print(f"{season} {game.gameId}: retained for retry: {error}", flush=True)
                if consecutive_failures >= failure_limit:
                    print(f"{season}: circuit open after {failure_limit} consecutive failures", flush=True)
                    break
            if index % 10 == 0:
                publish()
    finally:
        # Includes KeyboardInterrupt; completed work must not wait for ten games.
        publish()
    print(f"{season}: published {len(done)}/{len(expected)} games; {len(failures)} failures", flush=True)
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons", nargs="+", required=True)
    parser.add_argument("--max-new-games", type=int)
    parser.add_argument("--cached-only", action="store_true")
    args = parser.parse_args()
    if args.max_new_games is not None and args.max_new_games <= 0:
        parser.error("--max-new-games must be positive")
    failures = []
    for season in args.seasons:
        failures.extend(backfill_season(season, args.max_new_games, args.cached_only))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
