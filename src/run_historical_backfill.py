"""Single-owner, resumable historical backfill with bounded outage backoff.

No scheduler. Git publication is opt-in and limited to validated milestones.
"""

import argparse
from datetime import datetime, timedelta, timezone
import fcntl
import json
from pathlib import Path
import time

from backfill_player_intelligence import backfill_season
from player_rating_dataset import PLAYER_INTELLIGENCE_DIR, load_game_catalog
from update_player_intelligence import load_existing_player_games
from historical_publication import MilestonePublication


def now():
    return datetime.now(timezone.utc)


def progress(seasons, output_dir):
    coverage = {}
    for season in seasons:
        processed = set(load_existing_player_games(season, output_dir).gameId)
        expected = set(load_game_catalog(season).gameId)
        if not processed.issubset(expected):
            raise ValueError(f"Saved {season} games are outside the regular-season catalog.")
        coverage[season] = {"processedGames": len(processed), "expectedGames": len(expected)}
    return coverage


def run_backfill(seasons, output_dir=PLAYER_INTELLIGENCE_DIR, batch_size=25,
                 failure_limit=3, cooldown=60, max_cooldown=900, max_rounds=0,
                 sleeper=time.sleep, publish_every_games=0):
    if not seasons or min(batch_size, failure_limit, cooldown) < 1 or max_cooldown < cooldown or max_rounds < 0 or publish_every_games < 0:
        raise ValueError("Invalid batch, retry, or round settings")
    if publish_every_games and Path(output_dir).resolve() != Path(PLAYER_INTELLIGENCE_DIR).resolve():
        raise ValueError("Automatic publication requires the canonical repository output directory")
    runtime = Path(output_dir) / ".runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / "runner.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Historical backfill already running; skipped.", flush=True)
            return 0
        path = runtime / "status.json"
        publication = (MilestonePublication(runtime / "publication.json", publish_every_games)
                       if publish_every_games else None)
        state = {"startedAt": now().isoformat(), "status": "running", "round": 0,
                 "lastProgressAt": None, "failureCount": 0, "recentFailures": [],
                 "scope": "Validated milestone publication" if publication else "Local historical checkpoints; not hosted publication"}

        def publish():
            ready = publication.update(state["coverage"]) if publication else True
            if publication:
                state["publication"] = publication.state
            return ready

        def save(status, **fields):
            state.update(fields, status=status, updatedAt=now().isoformat())
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(state, indent=2) + "\n")
            temporary.replace(path)

        delay = cooldown
        try:
            while True:
                state["coverage"] = progress(seasons, output_dir)
                publication_ready = publish()
                pending = [s for s in seasons if state["coverage"][s]["processedGames"] < state["coverage"][s]["expectedGames"]]
                if not pending:
                    if not publication_ready:
                        save("local_complete_publication_pending", nextRetryAt=None)
                        if max_rounds:
                            return 1
                        sleeper(60)
                        continue
                    save("complete", nextRetryAt=None)
                    return 0
                if max_rounds and state["round"] >= max_rounds:
                    save("incomplete", nextRetryAt=None)
                    return 1
                season = pending[0]
                before = state["coverage"][season]["processedGames"]
                state["round"] += 1
                save("running", season=season, nextRetryAt=None, waitReason=None)
                try:
                    failures = backfill_season(season, max_new_games=batch_size,
                        output_dir=output_dir, failure_limit=failure_limit)
                except BlockingIOError:
                    save("waiting", waitReason="checkpoint_lock",
                         nextRetryAt=(now() + timedelta(seconds=2)).isoformat())
                    sleeper(2)
                    continue
                state["coverage"] = progress(seasons, output_dir)
                after = state["coverage"][season]["processedGames"]
                if after > before:
                    state["lastProgressAt"] = now().isoformat()
                state["failureCount"] += len(failures)
                state["recentFailures"] = (state["recentFailures"] + [
                    {"season": season, "gameId": f["gameId"], "error": f["error"][:1000]}
                    for f in failures])[-20:]
                publication_ready = publish()
                if max_rounds and state["round"] >= max_rounds:
                    complete = all(c["processedGames"] == c["expectedGames"] for c in state["coverage"].values())
                    status = "complete" if complete and publication_ready else (
                        "local_complete_publication_pending" if complete else "incomplete")
                    save(status, nextRetryAt=None)
                    return 0 if complete and publication_ready else 1
                if failures or after == before:
                    save("waiting", retryDelaySeconds=delay,
                         nextRetryAt=(now() + timedelta(seconds=delay)).isoformat())
                    print(f"Source failures/no progress; retrying after {delay}s. Checkpoint saved.", flush=True)
                    sleeper(delay)
                    delay = min(delay * 2, max_cooldown)
                else:
                    delay = cooldown
                    save("running", nextRetryAt=None)
                    sleeper(2)
        except KeyboardInterrupt:
            state["coverage"] = progress(seasons, output_dir)
            save("interrupted", nextRetryAt=None)
            return 130
        except Exception as error:
            save("failed", error=str(error)[:1000], nextRetryAt=None)
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons", nargs="+", required=True)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--failure-limit", type=int, default=3)
    parser.add_argument("--cooldown", type=int, default=60)
    parser.add_argument("--max-cooldown", type=int, default=900)
    parser.add_argument("--max-rounds", type=int, default=0)
    parser.add_argument("--publish-every-games", type=int, default=0,
                        help="Opt-in publication per season after N new games, or at season completion (0 disables)")
    args = parser.parse_args()
    raise SystemExit(run_backfill(**vars(args)))
