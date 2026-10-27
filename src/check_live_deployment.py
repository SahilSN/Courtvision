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
from live_game_date import eligible_game_date, overnight_game

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
        # A cold acquisition may fail, then recover. Require the LAST two
        # observations to be valid and advancing; never ignore a final failure.
        advanced = len(observations) in (2, 3) and progression(*observations[-2:])
        games.append(dict(gameId=game_id, advanced=advanced, observations=observations))
    return dict(status='current_feed_passed' if games and all(g['advanced'] for g in games)
                else 'not_ready', games=games, canEnableLive=False,
                scope='Two or three bounded rounds of current public feeds and frozen CPU analysis; '
                      'not hosted browser/load, interruption-recovery, or release approval')


def check(game_ids, context_path, *, interval=16, fetcher=fetch_json,
          sleeper=time.sleep, artifacts_loader=load_cpu_artifacts, today=None,
          runtime_check=None, verified_pairs=None, rounds_count=2):
    if (not isinstance(game_ids, (list, tuple)) or not 1 <= len(game_ids) <= MAX_LIVE_GAMES
            or len(set(game_ids)) != len(game_ids)
            or any(not isinstance(g, str) or len(g) != 10 or not g.isdigit()
                   or not g.startswith('002' + CURRENT_SEASON[2:4]) for g in game_ids)
            or not 16 <= interval <= 30 or type(rounds_count) is not int or rounds_count not in (2, 3)):
        raise ValueError('Choose 1–4 unique current-season IDs, 2–3 rounds and a 16–30 second interval')
    bundle = json.loads(Path(context_path).read_text())
    now = datetime.now(ZoneInfo('America/New_York'))
    if ((bundle['gameDate'] != today if today is not None else
         not eligible_game_date(bundle['gameDate'], now)) or bundle.get('season') != CURRENT_SEASON
            or bundle.get('seasonType') != 'Regular Season'):
        raise ValueError('Current-day context required')
    games = []
    game_day = bundle['gameDate']
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
    for index in range(rounds_count):
        if index:
            sleeper(interval)
        try:
            board, _ = fetcher(BASE + 'scoreboard?dates=' + game_day.replace('-', ''))
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
                    if today is None and overnight_game(game_day, now):
                        raise ValueError('Previous-day game has not started')
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
    return dict(checkedAt=datetime.now(timezone.utc).isoformat(), gameDate=game_day,
                environment='local', **summarize(rounds, game_ids))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-ids', nargs='+', required=True)
    parser.add_argument('--context', type=Path, default=ROOT/'results/live_context'/f'{CURRENT_SEASON}_day_context_v1.json')
    parser.add_argument('--interval', type=int, default=16)
    parser.add_argument('--rounds', type=int, choices=(2, 3), default=2)
    args = parser.parse_args()
    report = check(args.game_ids, args.context, interval=args.interval, rounds_count=args.rounds)
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'current_feed_passed' else 1


def probe_progress(day, environment, game_ids):
    """Once-only owner diagnostic; current day only, no browser activation."""
    if not eligible_game_date(day):
        return dict(status='wrong_day', canEnableLive=False)
    context = ROOT/'results/live_context'/f'{CURRENT_SEASON}_day_context_v1.json'
    if json.loads(context.read_text()).get('gameDate') != day:
        return dict(status='wrong_day', canEnableLive=False)
    report = check(game_ids, context,
                   interval=30, rounds_count=3)
    # Never feed archived/controlled fixtures through the process-shared live
    # telemetry: that could falsely close a real mismatch episode. Controlled
    # retention tests remain a separate offline suite, not provider measurements.
    report['controlledRecovery'] = dict(status='not_run', scope='Separate offline verification; no synthetic live measurements')
    return {**report, 'environment': environment}


if __name__ == '__main__':
    raise SystemExit(main())
