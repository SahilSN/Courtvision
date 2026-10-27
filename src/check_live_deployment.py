"""Explicit, bounded current-feed readiness check. Never activates Live."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import runpy
import time
from zoneinfo import ZoneInfo

from cloud_live_analysis import analyze_live_snapshot
from daily_live_context import read_day_context
from feed_progress import FeedProgress
from live_refresh import current_event, summary_pair
from live_rollout import MAX_LIVE_GAMES
from live_snapshot_cache import LiveSnapshotCache
from offline_live_sample import load_cpu_artifacts
from probe_live_access import BASE, fetch_json
from season_config import CURRENT_SEASON

ROOT = Path(__file__).resolve().parents[1]


def progression(first, second):
    """Corrections, final-only checks, failures and stale cache are not progress."""
    if (first.get('status') != 'validated' or second.get('status') != 'validated'
            or first.get('sourceState') != 'in'
            or second.get('sourceState') not in ('in', 'post')):
        return False
    return (second['elapsed'] > first['elapsed'] or
            (second['elapsed'] == first['elapsed'] and second['action'] > first['action']))


def summarize(rounds, game_ids):
    games = []
    for game_id in game_ids:
        observations = [next((r for r in batch if r['gameId'] == game_id),
                             {'gameId': game_id, 'status': 'missing'}) for batch in rounds]
        advanced = len(observations) == 2 and progression(*observations)
        games.append(dict(gameId=game_id, advanced=advanced, observations=observations))
    return dict(status='current_feed_passed' if games and all(g['advanced'] for g in games)
                else 'not_ready', games=games, canEnableLive=False,
                scope='Two bounded rounds of current public feeds and frozen CPU analysis; '
                      'not hosted browser/load, interruption-recovery, or release approval')


def check(game_ids, context_path, *, interval=16, fetcher=fetch_json,
          sleeper=time.sleep, artifacts_loader=load_cpu_artifacts, today=None,
          runtime_check=None, verified_pairs=None):
    if (not isinstance(game_ids, (list, tuple)) or not 1 <= len(game_ids) <= MAX_LIVE_GAMES
            or len(set(game_ids)) != len(game_ids)
            or any(not isinstance(g, str) or len(g) != 10 or not g.isdigit()
                   or not g.startswith('002' + CURRENT_SEASON[2:4]) for g in game_ids)
            or not 16 <= interval <= 30):
        raise ValueError('Choose 1–4 unique current-season IDs and a 16–30 second interval')
    today = today or datetime.now(ZoneInfo('America/New_York')).date().isoformat()
    bundle = json.loads(Path(context_path).read_text())
    if (bundle['gameDate'] != today or bundle.get('season') != CURRENT_SEASON
            or bundle.get('seasonType') != 'Regular Season'):
        raise ValueError('Current-day context required')
    games = []
    # Verify the complete selection before any network/model work.
    for game_id in game_ids:
        game, = [g for g in bundle['games'] if g['gameId'] == game_id]
        read_day_context(context_path, game)
        games.append(game)
    runtime_check = runtime_check or runpy.run_path(str(ROOT/'src/live_runtime_gate.py'))['runtime_ready']
    if not runtime_check(ROOT):
        return dict(status='runtime_blocked', canEnableLive=False)
    artifacts = artifacts_loader()
    cache = LiveSnapshotCache(max_entries=MAX_LIVE_GAMES)
    tracker = FeedProgress(max_entries=MAX_LIVE_GAMES)
    rounds = []
    for index in range(2):
        if index:
            sleeper(interval)
        try:
            board, _ = fetcher(BASE + 'scoreboard?dates=' + today.replace('-', ''))
        except Exception as error:
            rounds.append([dict(gameId=g['gameId'], status='failed',
                                errorType=type(error).__name__) for g in games])
            continue

        def observe(game):
            started = time.monotonic()
            attempts = 0
            loaded_pair = None
            try:
                event = current_event(game, game['espnEventId'], fetcher=lambda url: (board, {}))
                state = event['competitions'][0]['status']['type']['state']
                if state == 'pre':
                    return dict(gameId=game['gameId'], status='pregame', attempts=0)
                def loader():
                    nonlocal attempts, loaded_pair
                    attempts += 1
                    loaded_pair = summary_pair(event, game['espnEventId'], fetcher=fetcher)
                    return loaded_pair
                result = analyze_live_snapshot(cache, game, context_path, loader, artifacts,
                                               tracker, as_of_date=today)
                if verified_pairs is not None and not result.snapshot.is_stale and loaded_pair is not None:
                    # Retain only the pair actually accepted by the full join,
                    # never a failed refresh or a separate asynchronous fetch.
                    from copy import deepcopy
                    verified_pairs[game['gameId']] = deepcopy(loaded_pair)
                last = result.snapshot.timeline.iloc[-1]
                return dict(gameId=game['gameId'], status='stale' if result.snapshot.is_stale else 'validated',
                            sourceState=state, attempts=attempts, states=len(result.predictions),
                            elapsed=float(last['elapsedGameTime']), action=int(last['actionNumber']),
                            homeScore=int(last['scoreHome']), awayScore=int(last['scoreAway']),
                            seconds=round(time.monotonic()-started, 3))
            except Exception as error:
                return dict(gameId=game['gameId'], status='failed', attempts=attempts,
                            errorType=type(error).__name__)

        with ThreadPoolExecutor(max_workers=len(games)) as pool:
            rounds.append(list(pool.map(observe, games)))
    return dict(checkedAt=datetime.now(timezone.utc).isoformat(), gameDate=today,
                environment='local', **summarize(rounds, game_ids))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-ids', nargs='+', required=True)
    parser.add_argument('--context', type=Path, default=ROOT/'results/live_context'/f'{CURRENT_SEASON}_day_context_v1.json')
    parser.add_argument('--interval', type=int, default=16)
    args = parser.parse_args()
    report = check(args.game_ids, args.context, interval=args.interval)
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'current_feed_passed' else 1


def probe_progress(day, environment, game_ids):
    """Once-only owner diagnostic; current day only, no browser activation."""
    if day != datetime.now(ZoneInfo('America/New_York')).date().isoformat():
        return dict(status='wrong_day', canEnableLive=False)
    pairs, artifacts = {}, []
    def load_artifacts():
        value = load_cpu_artifacts()
        artifacts.append(value)
        return value
    report = check(game_ids, ROOT/'results/live_context'/f'{CURRENT_SEASON}_day_context_v1.json',
                   interval=30, artifacts_loader=load_artifacts, verified_pairs=pairs)
    # Separate controlled failure evidence from real progression observations.
    # Reuse the exact accepted pair: a new HTTP fetch is not the test fixture.
    # No additional HTTP, activation, or viewer fault injection.
    try:
        from live_release_recovery import verify_recovery
        path = ROOT/'results/live_context'/f'{CURRENT_SEASON}_day_context_v1.json'
        bundle = json.loads(path.read_text())
        # Retention safety does not depend on the game clock advancing (e.g.
        # a timeout). Keep its result independent of the progression gate.
        selected = next(g for g in report.get('games', []) if g['gameId'] in pairs)
        game, = [g for g in bundle['games'] if g['gameId'] == selected['gameId']]
        report['controlledRecovery'] = verify_recovery(game, path,
            pairs[selected['gameId']], artifacts[0])
    except StopIteration:
        report['controlledRecovery'] = dict(status='not_run_no_validated_pair')
    except Exception as error:
        report['controlledRecovery'] = dict(status='failed', errorType=type(error).__name__)
    return {**report, 'environment': environment}


if __name__ == '__main__':
    raise SystemExit(main())
