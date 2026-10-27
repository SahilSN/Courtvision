"""Official, exact, dated roster identities. Never fetch from the viewer path."""

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from nba_api.stats.static import teams
from espn_live import normalize_name
from live_artifacts import read_json
from live_game_date import eligible_game_date
from season_config import CURRENT_SEASON


def roster_url(team_id, season):
    if (team_id not in {t['id'] for t in teams.get_teams()} or type(team_id) is not int
            or season != CURRENT_SEASON):
        raise ValueError('Invalid official roster scope')
    return f'https://stats.nba.com/stats/commonteamroster?TeamID={team_id}&Season={season}&LeagueID=00'


def normalize_roster(payload, team_id, season):
    """Validate independently supplied NBA IDs, never ESPN IDs or fuzzy names."""
    roster_url(team_id, season)
    params = payload['parameters']
    if params['TeamID'] != team_id or params['Season'] != season:
        raise ValueError('Official roster parameter mismatch')
    dataset, = [s for s in payload['resultSets'] if s['name'] == 'CommonTeamRoster']
    headers = dataset['headers']
    if len(headers) != len(set(headers)) or not {'TeamID','SEASON','PLAYER','PLAYER_ID'}.issubset(headers):
        raise ValueError('Invalid official roster headers')
    rows, people, names = [], set(), set()
    if not 1 <= len(dataset['rowSet']) <= 30:
        raise ValueError('Invalid official roster size')
    for row in dataset['rowSet']:
        if len(row) != len(headers):
            raise ValueError('Truncated official roster')
        item = dict(zip(headers, row))
        person, name = item['PLAYER_ID'], item['PLAYER']
        if 'LeagueID' in item and (type(item['LeagueID']) not in (int,str) or item['LeagueID'] not in (0,'0','00')):
            raise ValueError('Wrong official roster league')
        if (item['TeamID'] != team_id or type(item['SEASON']) not in (int, str)
                or item['SEASON'] not in (season, int(season[:4]), season[:4])
                or type(person) is not int or not 0 < person < 1_000_000_000
                or not isinstance(name, str) or not 1 <= len(name) <= 100
                or any(ord(c) < 32 for c in name) or not normalize_name(name)
                or person in people or normalize_name(name) in names):
            raise ValueError('Ambiguous or wrong-scope official roster row')
        people.add(person); names.add(normalize_name(name))
        rows.append(dict(teamId=team_id, personId=person, fullName=name))
    return rows


def validate_roster_artifact(bundle, season, game_date):
    if (type(bundle['schemaVersion']) is not int or bundle['schemaVersion'] != 1 or bundle['season'] != season
            or bundle['gameDate'] != game_date or bundle['source'] != 'NBA CommonTeamRoster'
            or bundle['seasonType'] != 'Regular Season'):
        raise ValueError('Invalid dated roster artifact')
    checked = datetime.fromisoformat(bundle['checkedAt'])
    if checked.tzinfo is None:
        raise ValueError('Roster timestamp must be aware')
    if not isinstance(bundle['teams'], list) or len(bundle['teams']) > 8:
        raise ValueError('Oversized roster artifact')
    seen = set()
    for team in bundle['teams']:
        team_id = team['teamId']
        if team_id in seen or team['source'] != roster_url(team_id, season):
            raise ValueError('Duplicate or unofficial roster team')
        seen.add(team_id)
        if team['status'] not in ('verified', 'unavailable'):
            raise ValueError('Invalid roster status')
        rows = team['players']
        if team['status'] == 'unavailable':
            if rows:
                raise ValueError('Unavailable roster cannot supply identities')
            continue
        # Reuse the endpoint contract for persisted rows as well.
        normalize_roster(dict(parameters=dict(TeamID=team_id, Season=season), resultSets=[dict(
            name='CommonTeamRoster', headers=['TeamID','SEASON','PLAYER','PLAYER_ID'],
            rowSet=[[p['teamId'],season,p['fullName'],p['personId']] for p in rows])]), team_id, season)
    return bundle


@lru_cache(maxsize=4)
def _read_rosters(path, modified, size, season, game_date):
    # mtime+size invalidates cached identities on atomic publication, without
    # parsing a complete roster for every participant in every play.
    return validate_roster_artifact(read_json(path), season, game_date)


def roster_candidates(name, season, team_id, game_date, *, path=None, now=None):
    """Missing/stale/corrupt data provides NO extra identity; legacy stays intact."""
    if season != CURRENT_SEASON or not eligible_game_date(game_date, now):
        return set()
    path = Path(path) if path is not None else (
        Path(__file__).resolve().parents[1]/'results/live_context'/f'{season}_roster_identities_v1.json')
    try:
        stat = path.stat()
        bundle = _read_rosters(str(path), stat.st_mtime_ns, stat.st_size, season, game_date)
        checked = datetime.fromisoformat(bundle['checkedAt'])
        instant = now or datetime.now(timezone.utc)
        if not 0 <= (instant - checked).total_seconds() <= 36*3600:
            return set()
        matches = [t for t in bundle['teams'] if t['teamId'] == team_id and t['status'] == 'verified']
        return {p['personId'] for t in matches for p in t['players']
                if normalize_name(p['fullName']) == normalize_name(name)}
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return set()
