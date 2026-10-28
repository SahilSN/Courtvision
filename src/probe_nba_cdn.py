"""Two-request official NBA CDN access check; never activates a provider."""

from datetime import datetime, timezone
from pathlib import Path

from cloud_espn_adapter import validate_canonical
from live_artifacts import read_json
from probe_live_access import fetch_json
from season_config import CURRENT_SEASON


def fetch_cdn_pair(canonical, fetcher=fetch_json):
    validate_canonical(canonical)
    result = {}
    for section in ('boxscore', 'playbyplay'):
        url = ('https://cdn.nba.com/static/json/liveData/'
               f'{section}/{section}_{canonical["gameId"]}.json')
        payload, _ = fetcher(url)
        game = payload['game']
        if game['gameId'] != canonical['gameId']:
            raise ValueError('NBA CDN game identity mismatch')
        if section == 'boxscore' and any(
                game[side+'Team']['teamId'] != canonical[side+'TeamId']
                for side in ('home','away')):
            raise ValueError('NBA CDN team identity mismatch')
        result[section] = payload
    return result


def probe_cdn(day, environment, game_ids, *, root=None, fetcher=fetch_json):
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    report = dict(checkedAt=datetime.now(timezone.utc).isoformat(), environment=environment,
                  scope='NBA CDN access only; not provider activation or feed/model certification',
                  status='failed')
    try:
        context = read_json(root/'results/live_context'/f'{CURRENT_SEASON}_day_context_v1.json')
        if context['gameDate'] != day or not isinstance(game_ids,list) or len(game_ids)!=1:
            raise ValueError('One explicit dated canonical game required')
        game, = [g for g in context['games'] if g['gameId']==game_ids[0]]
        report['gameId'] = game['gameId']
        pair = fetch_cdn_pair(game, fetcher)
        report.update(status='access_verified', actions=len(pair['playbyplay']['game']['actions']))
    except Exception as error:
        report['errorType'] = type(error).__name__
        if type(getattr(error,'code',None)) is int:
            report['httpStatus'] = error.code
    return report
