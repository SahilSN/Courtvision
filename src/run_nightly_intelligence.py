"""Mac nightly refresh with a process lock, rotating logs, and isolated data publication."""

import argparse
import contextlib
import fcntl
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone

from season_config import CURRENT_SEASON
from update_intelligence import ROOT_DIR, game_ids, read_published, refresh_intelligence
from daily_live_context import refresh_nightly_context as refresh_coverage
from live_artifacts import read_json


def published_paths(season=CURRENT_SEASON):
    return [
        f"results/season_intelligence/{season}_team_rating_games_v1.csv",
        f"results/season_intelligence/{season}_team_summary_v1.csv",
        f"results/season_intelligence/{season}_update_status_v1.json",
        f"results/player_intelligence/{season}_player_game_v1.csv",
        f"results/player_intelligence/{season}_player_ratings_v1.csv",
        f"results/live_context/{season}_coverage_v1.json",
        f"results/live_context/{season}_day_context_v1.json",
        f"results/live_context/{season}_roster_identities_v1.json",
        f"results/live_context/{season}_identity_review_v1.json",
        f"results/live_context/{season}_daily_live_v1.json",
    ]


def git(directory, *arguments, check=True):
    return subprocess.run(
        ["/usr/bin/git", *arguments], cwd=directory,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        capture_output=True, text=True, timeout=120, check=check,
    )


def publish_current_data(root=ROOT_DIR, season=CURRENT_SEASON):
    """Publish an allowlist from a temporary clone; never stage the user's checkout."""
    root = Path(root)
    runtime = root / "results" / ".runtime" / "nightly"
    runtime.mkdir(parents=True, exist_ok=True)
    remote = git(root, "remote", "get-url", "origin").stdout.strip()
    with tempfile.TemporaryDirectory(prefix="publish-", dir=runtime) as directory:
        checkout = Path(directory) / "repo"
        git(root, "clone", "--depth", "1", "--single-branch", "--branch", "main", remote, str(checkout))
        for relative in published_paths(season):
            source = root / relative
            destination = checkout / relative
            if not source.exists():
                continue
            if relative.endswith(('_roster_identities_v1.json','_identity_review_v1.json','_daily_live_v1.json')):
                try:
                    incoming = read_json(source)
                    context = read_json(root/f'results/live_context/{season}_day_context_v1.json')
                    if incoming['schemaVersion'] != 1 or incoming['season'] != season or incoming['gameDate'] != context['gameDate']:
                        raise ValueError('Wrong Live preparation date')
                    if relative.endswith('_roster_identities_v1.json'):
                        from official_live_rosters import validate_roster_artifact
                        validate_roster_artifact(incoming,season,context['gameDate'])
                    if relative.endswith('_daily_live_v1.json'):
                        from daily_live_policy import validate_daily_manifest
                        validate_daily_manifest(incoming,context)
                except (OSError,KeyError,TypeError,ValueError,IndexError):
                    logging.getLogger('courtvision.nightly').warning('Skipping invalid optional Live preparation artifact')
                    continue
            if relative.endswith('_coverage_v1.json'):
                incoming = json.loads(source.read_text())
                if (incoming['season'] != season or incoming['scope'] != 'prior-results-cross-check'
                        or incoming['seasonType'] != 'Regular Season'):
                    raise ValueError('Invalid coverage artifact context')
                if destination.exists() and json.loads(destination.read_text())['completeThrough'] > incoming['completeThrough']:
                    raise ValueError('Refusing to regress published coverage')
            if relative.endswith('_day_context_v1.json'):
                incoming = json.loads(source.read_text())
                if incoming['season'] != season or incoming['seasonType'] != 'Regular Season':
                    raise ValueError('Invalid daily context season')
                if destination.exists() and json.loads(destination.read_text())['gameDate'] > incoming['gameDate']:
                    raise ValueError('Refusing to regress published day context')
            if relative.endswith(("_player_game_v1.csv", "_team_rating_games_v1.csv")):
                if not game_ids(read_published(destination)).issubset(game_ids(read_published(source))):
                    raise ValueError("Refusing to publish fewer games than are already on GitHub.")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            git(checkout, "add", "--", relative)
        if git(checkout, "diff", "--cached", "--quiet", check=False).returncode == 0:
            return "No published data changes"
        git(checkout, "-c", "user.name=Courtvision Nightly Updater",
            "-c", "user.email=courtvision-updater@users.noreply.github.com",
            "commit", "-m", f"update {season} intelligence from Mac nightly job")
        # Fail safely if main changes concurrently; the next nightly run clones it again.
        git(checkout, "push", "origin", "HEAD:main")
        return git(checkout, "rev-parse", "HEAD").stdout.strip()


class LogStream:
    def __init__(self, logger):
        self.logger = logger
        self.buffer = ""

    def write(self, text):
        self.buffer += text
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            if line:
                self.logger.info(line)
        return len(text)

    def flush(self):
        if self.buffer:
            self.logger.info(self.buffer)
            self.buffer = ""


def nightly_due(previous, now=None):
    now = now or datetime.now().astimezone()
    cutoff = now.replace(hour=1, minute=0, second=0, microsecond=0)
    if now < cutoff:
        cutoff -= timedelta(days=1)
    try:
        completed = datetime.fromisoformat(previous['finishedAt'])
        return not (previous.get('status') == 'success' and completed.tzinfo is not None
                    and cutoff <= completed <= now)
    except (KeyError, ValueError, TypeError, AttributeError):
        return True


def run_nightly(root=ROOT_DIR, publish=True, scheduled=False, refresher=refresh_intelligence,
                publisher=publish_current_data, coverage_checker=None):
    root = Path(root)
    runtime = root / "results" / ".runtime" / "nightly"
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / "update.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Nightly update already running; skipped.")
            return 0
        status_path = runtime / "status.json"
        try:
            previous = read_json(status_path)
        except (OSError, ValueError, TypeError):
            previous = {}  # Missing/corrupt saved evidence must not suppress catch-up.
        if scheduled and not nightly_due(previous):
            print("This nightly update already completed successfully; skipped.")
            return 0
        logger = logging.getLogger("courtvision.nightly")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        handler = RotatingFileHandler(runtime / "updates.log", maxBytes=2_000_000, backupCount=3)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        result = {"startedAt": datetime.now(timezone.utc).isoformat(), "status": "running"}
        stream = LogStream(logger)
        code = 1
        try:
            logger.info("Starting nightly team and player refresh")
            with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
                health = refresher(root=root)
            incomplete = any(health.get('pipelines',{}).get(name,{}).get('status') != 'success'
                             for name in ('teams','players'))
            try:
                result['recordCoverage'] = (coverage_checker or refresh_coverage)(root=root)
                preparation = result['recordCoverage'].get('livePreparation')
                if preparation is not None:
                    result['livePreparationStatus'] = preparation['status']
                    if preparation['status'] != 'prepared':
                        logger.warning('Live preparation %s; intelligence publication continues with strict Live validation',
                                       preparation['status'])
            except Exception as error:
                result['recordCoverage'] = {'status': 'failed', 'error': type(error).__name__}
                logger.warning('Record coverage check failed (%s); retaining last artifact', type(error).__name__)
                incomplete = True
            result["refreshStatus"] = "incomplete" if incomplete else "success"
            if publish:
                result["publication"] = publisher(root=root)
                logger.info("Publication: %s", result["publication"])
            result["status"] = "incomplete" if incomplete else "success"
            code = 1 if incomplete else 0
        except Exception as error:
            result.update(status="failed", error=str(error))
            logger.exception("Nightly job failed")
        finally:
            stream.flush()
            result["finishedAt"] = datetime.now(timezone.utc).isoformat()
            temporary = runtime / "status.json.tmp"
            temporary.write_text(json.dumps(result, indent=2) + "\n")
            os.replace(temporary, runtime / "status.json")
            logger.info("Finished: %s", result["status"])
            logger.removeHandler(handler)
            handler.close()
        print(f"Nightly update: {result['status']}. Logs: {runtime / 'updates.log'}")
        return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument("--scheduled", action="store_true")
    args = parser.parse_args()
    raise SystemExit(run_nightly(publish=not args.no_publish, scheduled=args.scheduled))


if __name__ == "__main__":
    main()
