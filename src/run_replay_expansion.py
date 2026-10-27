"""Mac-only bounded offline replay queue and nightly allowlisted publication."""

import argparse
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from zoneinfo import ZoneInfo

from live_artifacts import read_json, write_json
from replay_catalog import (INDEX, build_index, catalog_seasons, load_catalog_replay,
                            read_index, season_catalog)
from run_nightly_intelligence import git

HEALTH = 'results/replay_catalog/expansion_status_v1.json'


def fingerprint(paths):
    rows = []
    for path in paths:
        stat = path.stat()
        rows.append((str(path), stat.st_size, stat.st_mtime_ns))
    return sha256(repr(rows).encode()).hexdigest()


def seed_workspace(source, workspace):
    """Copy published metadata/artifacts only; never touch source datasets/index."""
    for entry in read_index(source).values():
        load_catalog_replay(entry, source)
        from replay_catalog import artifact_path
        relative = artifact_path(source, entry).relative_to(source)
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != (source / relative).read_bytes():
            raise ValueError('Source and prepared replay history disagree')
        if not target.exists():
            shutil.copy2(source / relative, target)
    metadata = workspace / 'results/season_intelligence'
    metadata.mkdir(parents=True, exist_ok=True)
    for path in (source / 'results/season_intelligence').glob('*_team_rating_games_v1.csv'):
        shutil.copy2(path, metadata / path.name)
    build_index(workspace)


def choose_batch(source, workspace, state, limit=5):
    prepared = read_index(workspace)
    for season in catalog_seasons(workspace):
        # 2024–25 has a reproduced systemic opening-state failure. Do not waste
        # inference on thousands of known-bad inputs; explicit repair is needed.
        if season == '2024-25':
            continue
        training = source / f'data/training/{season}_training_v4_base.csv'
        if not training.exists():
            continue
        games, invalid = season_catalog(season, workspace)
        if invalid:
            raise ValueError('Invalid prepared replay index')
        batch = []
        for game in games:
            gid = game['gameId']
            if gid in prepared:
                continue
            paths = [training, source / f'data/processed/{gid}.csv',
                     source / f'data/cache/box_score/v1/{gid}.pkl',
                     source / f'results/player_wpa_v3_{gid}_summary.csv',
                     source / 'models/win_probability_mlp_v7.pt',
                     source / 'models/win_probability_scaler_v7.pkl']
            if not all(p.is_file() and not p.is_symlink() for p in paths):
                continue
            signature = fingerprint(paths)
            old = state['games'].get(gid, {})
            if old.get('nextRetry', 0) > time.time():
                continue
            if old.get('status') == 'blocked' and old.get('fingerprint') == signature:
                continue
            batch.append((gid, signature))
            if len(batch) >= limit:
                break
        if batch:
            return season, batch
    return None, []


def publication_due(state, now):
    local = now.astimezone(ZoneInfo('America/Los_Angeles'))
    return ((local.hour, local.minute) >= (1, 30)
            and state.get('publishedDay') != local.date().isoformat()
            and now.timestamp() >= state.get('nextPublishRetry', 0))


def publish(source, workspace, health):
    """Merge immutable new artifacts into latest remote main, never user index."""
    remote = git(source, 'remote', 'get-url', 'origin').stdout.strip()
    with tempfile.TemporaryDirectory(prefix='publish-', dir=workspace.parent) as directory:
        checkout = Path(directory) / 'repo'
        git(source, 'clone', '--depth', '1', '--single-branch', '--branch', 'main', remote, str(checkout))
        existing = read_index(checkout)
        for gid, entry in read_index(workspace).items():
            load_catalog_replay(entry, workspace)
            if gid in existing:
                load_catalog_replay(existing[gid], checkout)
                if entry['sha256'] != existing[gid]['sha256']:
                    raise ValueError('Refusing to alter already-published replay')
                continue
            from replay_catalog import artifact_path
            relative = artifact_path(workspace, entry).relative_to(workspace)
            target = checkout / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(workspace / relative, target)
            git(checkout, 'add', '--', str(relative))
        index = build_index(checkout)
        for entry in index['games']:
            load_catalog_replay(entry, checkout)
        write_json(checkout / HEALTH, {**health, 'publishedReplayCount': len(index['games'])})
        git(checkout, 'add', '--', INDEX, HEALTH)
        if git(checkout, 'diff', '--cached', '--quiet', check=False).returncode:
            git(checkout, '-c', 'user.name=Courtvision Replay Publisher',
                '-c', 'user.email=courtvision-updater@users.noreply.github.com',
                'commit', '-m', 'publish validated offline replay expansion')
            git(checkout, '-c', 'http.postBuffer=16777216', 'push', 'origin', 'HEAD:main')
        return git(checkout, 'rev-parse', 'HEAD').stdout.strip()


def run(source, publish_now=False, prepare=True, now=None):
    source = Path(source).resolve()
    now = now or datetime.now(timezone.utc)
    runtime = source / 'results/.runtime/replay-expansion'
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / 'worker.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state_path = runtime / 'state.json'
        # Corrupt state fails closed, never silently retries every blocked input.
        state = read_json(state_path) if state_path.exists() else {'games': {}, 'dailyAttempts': 0}
        day = now.astimezone(ZoneInfo('America/Los_Angeles')).date().isoformat()
        if state.get('attemptDay') != day:
            state.update(attemptDay=day, dailyAttempts=0)
        workspace = runtime / 'prepared'
        if shutil.disk_usage(runtime).free < 2_000_000_000:
            raise OSError('Replay expansion requires at least 2 GB free disk space')
        seed_workspace(source, workspace)
        if prepare and state['dailyAttempts'] < 200:
            season, batch = choose_batch(source, workspace, state, min(5, 200 - state['dailyAttempts']))
            if batch:
                # Reserve attempts before spawning: crash/restart cannot defeat daily cap.
                state['dailyAttempts'] += len(batch)
                write_json(state_path, state)
                args = [sys.executable, '-B', str(source / 'src/rebuild_saved_replays.py'),
                        '--root', str(workspace), '--cache-root', str(source),
                        '--season', season, '--from-catalog']
                for gid, _ in batch:
                    args.extend(['--game-id', gid])
                log = runtime / 'last-batch.log'
                with log.open('w') as output:
                    try:
                        subprocess.run(args, cwd=source, stdout=output, stderr=subprocess.STDOUT,
                                       timeout=180, check=True,
                                       env={**os.environ, 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'})
                    except (subprocess.SubprocessError, OSError) as error:
                        state['lastBatchError'] = type(error).__name__
                    else:
                        state.pop('lastBatchError', None)
                indexed = read_index(workspace)
                report_path = workspace / f'results/.runtime/replay-rebuild/{season}.json'
                report = read_json(report_path).get('games', {}) if report_path.exists() else {}
                for gid, signature in batch:
                    status = ('prepared' if gid in indexed else
                              'blocked' if report.get(gid, {}).get('status') == 'blocked' else 'pending')
                    state['games'][gid] = {'fingerprint': signature, 'status': status,
                                           'nextRetry': now.timestamp() + 3600 if status == 'pending' else 0}
        health = {'schemaVersion': 1, 'checkedAt': now.isoformat(),
                  'preparedReplayCount': len(read_index(workspace)),
                  'blockedGames': sum(g['status'] == 'blocked' for g in state['games'].values()),
                  'pausedSeasons': ['2024-25'], 'dailyAttempts': state['dailyAttempts'],
                  'schedule': 'Mac: bounded batch every 30 minutes; publish nightly after 1:30 a.m. Pacific'}
        state['health'] = health
        write_json(state_path, state)
        if publish_now or publication_due(state, now):
            try:
                state['publication'] = publish(source, workspace, health)
            except Exception as error:
                state.update(publicationState='retry_pending', publicationError=type(error).__name__,
                             nextPublishRetry=now.timestamp() + 3600)
            else:
                state.update(publicationState='success', publishedDay=day,
                             lastPublishAt=now.isoformat(), nextPublishRetry=0)
                state.pop('publicationError', None)
        write_json(state_path, state)
        return {'health': health, 'publicationState': state.get('publicationState', 'not_due')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--publish-now', action='store_true')
    parser.add_argument('--publish-only', action='store_true')
    args = parser.parse_args()
    try:
        os.nice(10)
        print(run(args.root, args.publish_now, not args.publish_only))
    except BlockingIOError:
        print('Replay worker already running; skipped overlap.')
