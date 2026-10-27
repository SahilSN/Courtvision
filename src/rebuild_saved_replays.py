"""Bounded offline repair/export of trusted saved replays; never modify source caches."""

import argparse
import fcntl
from contextlib import ExitStack, redirect_stdout
import io
from pathlib import Path
import pickle
import shutil
import tempfile
from unittest.mock import patch

from live_artifacts import write_json, read_json
from prepare_replay_catalog import prepare
from replay_catalog import valid_identity, season_catalog, read_index


def rebuild(root, cache_root, season, game_ids, from_catalog=False):
    runtime = Path(root) / 'results/.runtime/replay-export'
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / 'batch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _rebuild(root, cache_root, season, game_ids, from_catalog)


def _rebuild(root, cache_root, season, game_ids, from_catalog=False):
    if not 1 <= len(game_ids) <= 5 or len(set(game_ids)) != len(game_ids):
        raise ValueError('Select 1–5 distinct saved games')
    root, cache_root = Path(root), Path(cache_root)
    for gid in game_ids:
        valid_identity(gid, season, f'{season[:4]}-10-01')
    catalog = {}
    if from_catalog:
        rows, invalid = season_catalog(season, root)
        if invalid:
            raise ValueError('Published index must be valid before rebuilding')
        catalog = {row['gameId']: row for row in rows}
        if any(gid not in catalog for gid in game_ids):
            raise ValueError('Only catalogued completed games can be prepared')
    # Import only for operator execution; hosted readers never import this module.
    import live_analysis as analysis
    import player_impact as impact

    status_path = root / f'results/.runtime/replay-rebuild/{season}.json'
    try:
        previous = read_json(status_path).get('games', {})
    except (OSError, ValueError, TypeError):
        previous = {}
    report = {'season': season, 'scope': 'offline-completed-replays-only',
              'games': previous if isinstance(previous, dict) else {}}
    for gid in game_ids:
        try:
            if gid in read_index(root):
                from replay_catalog import load_catalog_replay
                load_catalog_replay(read_index(root)[gid], root)
                report['games'][gid] = {'status': 'alreadyPrepared'}
                continue
            with tempfile.TemporaryDirectory(prefix='replay-rebuild-') as directory:
                stage = Path(directory)
                relative = Path(f'data/cache/analysis/v1_v7/{season}_{gid}_top3.pkl')
                if from_catalog:
                    result = {'game_date': catalog[gid]['date']}
                else:
                    with (cache_root / relative).open('rb') as handle:
                        payload = pickle.load(handle)  # Trusted operator-owned local cache only.
                    result = payload['result']
                    if (payload['cache_version'] != 'v1_v7' or result['game_id'] != gid
                            or not result['is_final']):
                        raise ValueError('Wrong/nonfinal saved cache')
                valid_identity(gid, season, str(result['game_date']))
                box = Path(f'data/cache/box_score/v1/{gid}.pkl')
                (stage / box).parent.mkdir(parents=True)
                shutil.copy2(cache_root / box, stage / box)
                with ExitStack() as stack:
                    for name, value in [('ROOT_DIR', cache_root),
                                        ('MODEL_PATH', cache_root / 'models/win_probability_mlp_v7.pt'),
                                        ('SCALER_PATH', cache_root / 'models/win_probability_scaler_v7.pkl')]:
                        stack.enter_context(patch.object(analysis, name, value))
                    for name in ('fetch_live_play_by_play', 'fetch_true_live_play_by_play',
                                 'fetch_team_record_before_game'):
                        stack.enter_context(patch.object(analysis, name,
                            side_effect=RuntimeError('Offline rebuild cannot acquire remote data')))
                    analysis.load_local_season_data.cache_clear()
                    analysis.load_live_artifacts.cache_clear()
                    # Re-run original frozen pipeline, never fill/clamp missing probabilities.
                    result = analysis.analyze_live_game(gid, season, result['game_date'], assume_final=True)
                    if from_catalog:
                        from nba_api.stats.static import teams
                        names = {team['id']: team['abbreviation'] for team in teams.get_teams()}
                        expected = catalog[gid]
                        if (result['game_date'] != expected['date']
                                or names[result['home_team_id']] != expected['home']
                                or names[result['away_team_id']] != expected['away']):
                            raise ValueError('Offline analysis disagrees with completed catalog identity')
                    payload = {'cache_version': 'v1_v7', 'result': result}
                    (stage / relative).parent.mkdir(parents=True, exist_ok=True)
                    with (stage / relative).open('wb') as handle:
                        pickle.dump(payload, handle)
                    summary = Path(f'results/player_wpa_v3_{gid}_summary.csv')
                    (stage / summary).parent.mkdir(parents=True, exist_ok=True)
                    if (cache_root / summary).exists():
                        shutil.copy2(cache_root / summary, stage / summary)
                    else:
                        for name, value in [('TRAINING_DIR', cache_root / 'data/training'),
                                            ('PROCESSED_DIR', cache_root / 'data/processed'),
                                            ('RESULTS_DIR', stage / 'results'),
                                            ('MODEL_PATH', cache_root / 'models/win_probability_mlp_v7.pt'),
                                            ('SCALER_PATH', cache_root / 'models/win_probability_scaler_v7.pkl')]:
                            stack.enter_context(patch.object(impact, name, value))
                        with redirect_stdout(io.StringIO()):
                            impact.analyze_player_impact(gid, season)
                    prepare(root, stage, season, [gid])
                report['games'][gid] = {'status': 'prepared'}
        except Exception as error:
            report['games'][gid] = {'status': 'blocked', 'errorType': type(error).__name__,
                                    'reason': str(error)[:300]}
        finally:
            analysis.load_local_season_data.cache_clear()
            analysis.load_live_artifacts.cache_clear()
        write_json(status_path, report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--cache-root', type=Path, required=True)
    parser.add_argument('--season', required=True)
    parser.add_argument('--game-id', action='append', required=True)
    parser.add_argument('--from-catalog', action='store_true', help='Build from explicit completed catalog identities instead of saved analysis')
    args = parser.parse_args()
    print(rebuild(args.root, args.cache_root, args.season, args.game_id, args.from_catalog))
