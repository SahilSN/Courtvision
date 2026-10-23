"""Validate and publish only historical player CSV pairs from a consistent snapshot."""

import argparse
import fcntl
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import pandas as pd

from player_rating import build_player_ratings
from player_rating_dataset import validate_player_game_dataset
from run_nightly_intelligence import git
from season_config import CURRENT_SEASON
from update_intelligence import ROOT_DIR, read_published


def historical_season(season):
    match = re.fullmatch(r"(\d{4})-(\d{2})", season)
    if not match or int(match[2]) != (int(match[1]) + 1) % 100 or int(match[1]) >= int(CURRENT_SEASON[:4]):
        raise ValueError("Only completed historical regular seasons may be published here.")
    return season


def canonical(frame, keys):
    result = frame.sort_values(keys).reset_index(drop=True).sort_index(axis=1)
    return result.astype(object).where(result.notna(), None)


def validate_checkpoint(season, games, ratings, expected, previous=None):
    historical_season(season)
    validate_player_game_dataset(games)
    if games.empty or not games.season.eq(season).all():
        raise ValueError("Missing or mixed-season player checkpoint")
    if not expected or not set(games.gameId).issubset(expected):
        raise ValueError("Checkpoint contains games outside the published regular-season catalog")
    # Reconstruct every rating, rank, eligibility flag, and aggregate from this
    # exact snapshot; a crash between the two CSV replacements must be rejected.
    pd.testing.assert_frame_equal(canonical(ratings, ["personId"]),
        canonical(build_player_ratings(games), ["personId"]),
        check_dtype=False, check_exact=False, rtol=1e-9, atol=1e-9)
    if previous is not None and not previous.empty:
        validate_player_game_dataset(previous)
        keys = ["gameId", "personId"]
        old = previous.set_index(keys)
        new = games.set_index(keys)
        if not old.index.isin(new.index).all():
            raise ValueError("Refusing to remove already-published player appearances")
        pd.testing.assert_frame_equal(old.sort_index().sort_index(axis=1),
            new.loc[old.index].sort_index().sort_index(axis=1),
            check_dtype=False, check_exact=False, rtol=1e-9, atol=1e-9)


def publish_historical(seasons, root=ROOT_DIR):
    root = Path(root)
    seasons = list(dict.fromkeys(historical_season(s) for s in seasons))
    if not seasons:
        raise ValueError("Choose at least one historical season")
    output = root / "results/player_intelligence"
    runtime = root / "results/.runtime/historical-publication"
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / "publish.lock").open("a") as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        remote = git(root, "remote", "get-url", "origin").stdout.strip()
        with tempfile.TemporaryDirectory(prefix="checkpoint-", dir=runtime) as directory:
            checkout = Path(directory) / "repo"
            git(root, "clone", "--depth", "1", "--single-branch", "--branch", "main", remote, str(checkout))
            previous = {s: read_published(checkout / "results/player_intelligence" / f"{s}_player_game_v1.csv") for s in seasons}
            local_runtime = output / ".runtime"
            local_runtime.mkdir(parents=True, exist_ok=True)
            # Snapshot all selected pairs under the same lock used by writers.
            # Busy writers cause a safe retry, never a partially copied pair.
            with (local_runtime / "checkpoint.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
                for season in seasons:
                    for suffix in ("player_game_v1.csv", "player_ratings_v1.csv"):
                        relative = Path("results/player_intelligence") / f"{season}_{suffix}"
                        (checkout / relative).parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(root / relative, checkout / relative)
            for season in seasons:
                target = checkout / "results/player_intelligence"
                games = read_published(target / f"{season}_player_game_v1.csv")
                ratings = pd.read_csv(target / f"{season}_player_ratings_v1.csv")
                history = read_published(checkout / "results/season_intelligence" / f"{season}_team_rating_games_v1.csv")
                validate_checkpoint(season, games, ratings, set(history.gameId), previous[season])
                for suffix in ("player_game_v1.csv", "player_ratings_v1.csv"):
                    git(checkout, "add", "--", f"results/player_intelligence/{season}_{suffix}")
            if git(checkout, "diff", "--cached", "--quiet", check=False).returncode == 0:
                return "No historical checkpoint changes"
            git(checkout, "-c", "user.name=Courtvision Historical Publisher",
                "-c", "user.email=courtvision-updater@users.noreply.github.com",
                "commit", "-m", "publish validated player checkpoints: " + ", ".join(seasons))
            # No force-push/rebase: concurrent main updates require a fresh retry.
            # Command-local buffering avoids chunked-transfer failures seen on
            # this Mac's larger CSV uploads. No global config or TLS changes.
            git(checkout, "-c", "http.postBuffer=16777216", "push", "origin", "HEAD:main")
            return git(checkout, "rev-parse", "HEAD").stdout.strip()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons", nargs="+", required=True)
    args = parser.parse_args()
    try:
        print(publish_historical(args.seasons))
    except subprocess.CalledProcessError as error:
        parser.exit(1, "Checkpoint Git operation failed; no force-push was attempted.\n"
                    + (error.stderr or str(error))[-2000:] + "\n")
