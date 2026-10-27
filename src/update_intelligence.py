"""Refresh independent intelligence pipelines and publish their observable health."""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from season_config import CURRENT_SEASON, CURRENT_SEASON_TYPE
from update_live_season import fetch_completed_season_games
from live_artifacts import read_json


ROOT_DIR = Path(__file__).resolve().parents[1]


def load_update_status(path):
    try:
        saved = read_json(path)
        pipelines = saved.get('pipelines',{})
        if not isinstance(pipelines,dict) or any(not isinstance(item,dict) for item in pipelines.values()):
            raise ValueError('Invalid pipeline status')
        return saved
    except (OSError,ValueError,TypeError):
        return {}


def read_published(path):
    return pd.read_csv(path, dtype={"gameId": str}) if path.exists() else pd.DataFrame()


def game_ids(frame):
    return set(frame["gameId"].astype(str).str.zfill(10)) if not frame.empty else set()


def refresh_intelligence(root=ROOT_DIR, season=CURRENT_SEASON, timeout=30,
                         discovery=fetch_completed_season_games,
                         team_runner=None, player_runner=None):
    root = Path(root)
    status_path = root / "results" / "season_intelligence" / f"{season}_update_status_v1.json"
    previous = load_update_status(status_path)
    checked_at = datetime.now(timezone.utc).isoformat()
    paths = {
        "teams": root / "results" / "season_intelligence" / f"{season}_team_rating_games_v1.csv",
        "players": root / "results" / "player_intelligence" / f"{season}_player_game_v1.csv",
    }
    published = {name: read_published(path) for name, path in paths.items()}
    source_error = None
    games = pd.DataFrame()
    try:
        games = discovery(season=season, season_type=CURRENT_SEASON_TYPE, timeout=timeout)
        discovered = game_ids(games)
        known = set().union(*(game_ids(frame) for frame in published.values()))
        if not known.issubset(discovered):
            raise ValueError("Completed-game discovery omitted previously published games; retaining published data.")
    except Exception as error:
        source_error = str(error)

    status = {"season": season, "checkedAt": checked_at, "sourceError": source_error, "pipelines": {}}
    for name in ("teams", "players"):
        frame = published[name]
        error = source_error
        failures = []
        if error is None:
            try:
                if name == "teams":
                    if team_runner is None:
                        from update_live_season import update_live_season
                        team_runner = update_live_season
                    result = team_runner(
                        season=season, completed_games=games, timeout=timeout,
                        runtime_root=root / "results" / ".runtime" / "team_rating",
                        publish_dir=paths[name].parent,
                    )
                    if result.get("history") is not None:
                        frame = result["history"]
                else:
                    if player_runner is None:
                        from update_player_intelligence import update_player_intelligence
                        player_runner = update_player_intelligence
                    result = player_runner(
                        season=season, completed_games=games, timeout=timeout,
                        output_dir=paths[name].parent,
                    )
                    frame = result["dataset"]
                    failures = result.get("failures", [])
            except Exception as pipeline_error:
                error = str(pipeline_error)
                frame = read_published(paths[name])
        processed = game_ids(frame)
        pending = sorted(game_ids(games) - processed) if source_error is None else None
        state = "failed" if error else "partial" if pending or failures else "success"
        last_success = previous.get("pipelines", {}).get(name, {}).get("lastSuccessfulCheckAt")
        if state == "success":
            last_success = checked_at
        dates = pd.to_datetime(frame["gameDate"], errors="raise") if not frame.empty else pd.Series(dtype="datetime64[ns]")
        status["pipelines"][name] = {
            "status": state, "checkedAt": checked_at,
            "lastSuccessfulCheckAt": last_success,
            "gamesThrough": dates.max().strftime("%Y-%m-%d") if not dates.empty else None,
            "processedGames": len(processed),
            "completedGames": len(game_ids(games)) if source_error is None else None,
            "pendingGameIds": pending, "failures": failures, "error": error,
        }
        print(f"{name}: {state}; processed={len(processed)}; pending={len(pending) if pending is not None else 'unknown'}", flush=True)
        if error:
            print(f"  {error}", flush=True)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = status_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(status, indent=2) + "\n")
    os.replace(temporary, status_path)
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()
    status = refresh_intelligence(timeout=args.timeout)
    if any(pipeline["status"] != "success" for pipeline in status["pipelines"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
