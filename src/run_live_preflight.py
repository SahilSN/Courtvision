"""Bounded Mac roster retries/review publication. Never changes pregame records or policy."""

import argparse
from datetime import datetime, timedelta, timezone
import fcntl
from pathlib import Path
import shutil
import tempfile

from daily_live_policy import active_games, validate_daily_manifest
from live_artifacts import read_json, write_json, digest
from official_live_rosters import validate_roster_artifact
from prepare_daily_live import prepare_daily_live
from run_nightly_intelligence import git
from season_config import CURRENT_SEASON


def paths():
    return [f'results/live_context/{CURRENT_SEASON}_{name}_v1.json'
            for name in ('roster_identities', 'identity_review', 'daily_live')]


def invariant(original, candidate, context):
    validate_daily_manifest(original, context)
    validate_daily_manifest(candidate, context)
    for key in ('issuedAt', 'expiresAt', 'contextDigest', 'gameIds', 'gameDate', 'season', 'seasonType'):
        if original[key] != candidate[key]:
            raise ValueError('Preflight cannot change rollout lifetime, games or pregame context')


def semantic(value):
    if isinstance(value, dict):
        return {k: semantic(v) for k, v in value.items() if k not in ('checkedAt',)}
    if isinstance(value, list):
        return [semantic(v) for v in value]
    return value


def publish_preflight(source, stage, context, original):
    remote = git(source, 'remote', 'get-url', 'origin').stdout.strip()
    with tempfile.TemporaryDirectory(prefix='live-preflight-publish-') as directory:
        checkout = Path(directory) / 'repo'
        git(source, 'clone', '--depth', '1', '--single-branch', '--branch', 'main', remote, str(checkout))
        context_path = f'results/live_context/{CURRENT_SEASON}_day_context_v1.json'
        remote_context = read_json(checkout / context_path)
        if digest(remote_context) != digest(context):
            raise ValueError('Published day context changed; retry with original dated records')
        remote_manifest = read_json(checkout / paths()[2])
        invariant(original, remote_manifest, context)
        old_roster=read_json(checkout / paths()[0])
        new_roster=read_json(stage / paths()[0])
        for old_team in old_roster['teams']:
            fresh=next((t for t in new_roster['teams'] if t['teamId']==old_team['teamId']),None)
            observed=datetime.fromisoformat(old_team.get('checkedAt',old_roster['checkedAt']))
            if old_team['status']=='verified' and 0 <= (datetime.now(timezone.utc)-observed).total_seconds() <= 36*3600 and (fresh is None or fresh['status']!='verified'):
                raise ValueError('Refusing to discard a concurrently published verified roster')
            if fresh and datetime.fromisoformat(fresh.get('checkedAt',new_roster['checkedAt'])) < datetime.fromisoformat(old_team.get('checkedAt',old_roster['checkedAt'])):
                raise ValueError('Refusing to publish older roster evidence')
        for old_profile in old_roster.get('profiles', []):
            stamp = datetime.fromisoformat(old_profile['checkedAt'])
            if not 0 <= (datetime.now(timezone.utc)-stamp).total_seconds() <= 36*3600:
                continue
            fresh = next((p for p in new_roster.get('profiles', [])
                          if (p['teamId'],p['fullName']) == (old_profile['teamId'],old_profile['fullName'])), None)
            if (fresh is None or fresh['personId'] != old_profile['personId']
                    or datetime.fromisoformat(fresh['checkedAt']) < stamp):
                raise ValueError('Refusing to replace concurrent verified profile evidence')
        candidate = read_json(stage / paths()[2])
        invariant(remote_manifest, candidate, context)
        validate_roster_artifact(read_json(stage / paths()[0]), CURRENT_SEASON, context['gameDate'])
        for relative in paths():
            shutil.copy2(stage / relative, checkout / relative)
            git(checkout, 'add', '--', relative)
        if git(checkout, 'diff', '--cached', '--quiet', check=False).returncode:
            git(checkout, '-c', 'user.name=Courtvision Live Preflight',
                '-c', 'user.email=courtvision-updater@users.noreply.github.com',
                'commit', '-m', 'publish verified Live roster preflight and review queue')
            git(checkout, 'push', 'origin', 'HEAD:main')
        return git(checkout, 'rev-parse', 'HEAD').stdout.strip()


def run(root, *, now=None, preparer=prepare_daily_live, publisher=publish_preflight):
    root = Path(root)
    now = now or datetime.now(timezone.utc)
    runtime = root / 'results/.runtime/live-preflight'
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / 'worker.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        context_path = Path(f'results/live_context/{CURRENT_SEASON}_day_context_v1.json')
        context = read_json(root / context_path)
        original = read_json(root / paths()[2])
        # Preparation only. This does not set host opt-in or activate any game.
        allowed = active_games(root, {'COURTVISION_ENABLE_LIVE_BETA': '1'}, now)
        if not allowed:
            return {'status': 'inactive_or_expired'}
        games = [g for g in context['games'] if g['gameId'] in allowed]
        first = min(datetime.fromisoformat(g['scheduledAt']) for g in games)
        if now < first - timedelta(hours=1):
            return {'status': 'before_preflight_window'}
        status_path = runtime / 'status.json'
        state = read_json(status_path) if status_path.exists() else {}
        if state.get('nextRunAt', 0) > now.timestamp():
            return {'status': 'backoff'}
        state.update(checkedAt=now.isoformat(), nextRunAt=now.timestamp() + 900)
        write_json(status_path, state)
        with tempfile.TemporaryDirectory(prefix='stage-', dir=runtime) as directory:
            stage = Path(directory)
            (stage / context_path).parent.mkdir(parents=True)
            shutil.copy2(root / context_path, stage / context_path)
            if (root / paths()[0]).exists():
                shutil.copy2(root / paths()[0], stage / paths()[0])
            try:
                report = preparer(stage, now=now)
            except Exception as error:
                state.update(status='preparation_failed', errorType=type(error).__name__)
                write_json(status_path, state)
                return state
            candidate = read_json(stage / paths()[2])
            if candidate['gameIds'] != original['gameIds']:
                raise ValueError('Preflight cannot review a different selected slate')
            # Only readiness counters/observations change. Do not renew the beta.
            candidate.update({key: original[key] for key in
                              ('issuedAt','expiresAt','contextDigest','gameIds')})
            invariant(original, candidate, context)
            write_json(stage / paths()[2], candidate)
            signature = digest([semantic(read_json(stage / name)) for name in paths()])
            state.update(preparation=report, pending=read_json(stage / paths()[1])['pending'])
            # A timestamp-only refresh must not cause repeated cloud redeployments.
            if signature != state.get('publishedSignature'):
                try:
                    state['publication'] = publisher(root, stage, context, original)
                except Exception as error:
                    state.update(status='publication_retry', errorType=type(error).__name__)
                else:
                    state.update(status='published', publishedSignature=signature,
                                 lastPublishedAt=now.isoformat())
                    state.pop('errorType', None)
                    # Never copy over a newly replaced nightly context.
                    if digest(read_json(root / context_path)) == digest(context):
                        for name in paths():
                            write_json(root / name, read_json(stage / name))
            else:
                state['status'] = 'unchanged'
        write_json(status_path, state)
        return state


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        result = run(args.root)
        print({key: value for key, value in result.items() if key != 'pending'})
    except BlockingIOError:
        print('Live preflight already running; skipped overlap.')
