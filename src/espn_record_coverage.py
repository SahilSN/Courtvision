"""Cross-check prior NBA history against every ESPN calendar day; no live rollout."""

from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import time
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from nba_api.stats.static import teams

from cloud_espn_adapter import validate_canonical
from espn_live import ESPN_SCOREBOARD_URL, normalize_name
from season_config import CURRENT_SEASON


def fetch_day(day):
    with requests.get(ESPN_SCOREBOARD_URL, params={'dates': day.strftime('%Y%m%d'), 'limit': 1000},
                      timeout=5, allow_redirects=False, stream=True) as response:
        response.raise_for_status()
        if response.status_code != 200:
            raise ValueError('Unexpected scoreboard response')
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > 2_000_000:
                raise ValueError('Scoreboard exceeds size budget')
            chunks.append(chunk)
        return json.loads(b''.join(chunks))


def verify_coverage(history, season, through, loader=fetch_day, budget=90):
    """Evidence of agreement between two sources, not proof neither omits a game.

    Canonical NBA IDs come only from independently published history, matched by
    exact date and home/away teams. No ESPN ID is cast or synthesized as an NBA ID.
    """
    through = date.fromisoformat(through)
    end_year = int(season[:4]) + 1
    started = time.monotonic()
    first = loader(through)
    league = first['leagues'][0]
    if league['id'] != '46' or league['season']['year'] != end_year or league['season']['displayName'] != season:
        raise ValueError('Wrong ESPN league/season')
    start = date.fromisoformat(league['season']['startDate'][:10])
    if not 0 <= (through - start).days <= 300:
        raise ValueError('Invalid season coverage window')
    names = {normalize_name(t['full_name']): t for t in teams.get_teams()}
    names[normalize_name('LA Clippers')] = next(t for t in teams.get_teams() if t['abbreviation'] == 'LAC')
    observed, seen, days = {}, set(), []
    day = start
    while day <= through:
        if time.monotonic() - started > budget:
            raise ValueError('Coverage refresh exceeded time budget')
        payload = first if day == through else loader(day)
        metadata = payload['leagues'][0]
        if metadata['id'] != '46' or metadata['season']['year'] != end_year:
            raise ValueError('Mixed daily season metadata')
        events = payload['events']
        if not isinstance(events, list) or len(events) >= 1000:
            raise ValueError('Malformed or potentially truncated day')
        for event in events:
            if event['season']['year'] != end_year:
                raise ValueError('Wrong event season')
            if event['season']['type'] != 2:
                continue
            if event['id'] in seen:
                raise ValueError('Repeated event across daily responses')
            seen.add(event['id'])
            competition, = event['competitions']
            timestamp = datetime.fromisoformat(competition['date'].replace('Z', '+00:00'))
            if timestamp.tzinfo is None or timestamp.astimezone(ZoneInfo('America/New_York')).date() != day:
                raise ValueError('Scoreboard date mismatch')
            if competition['status']['type']['completed'] is not True:
                raise ValueError('Prior scheduled game is not final')
            competitors = competition['competitors']
            if len(competitors) != 2:
                raise ValueError('Invalid competitors')
            sides = {}
            for competitor in competitors:
                side = competitor['homeAway']
                if side not in ('home', 'away') or side in sides:
                    raise ValueError('Ambiguous sides')
                team = names[normalize_name(competitor['team']['displayName'])]
                score = competitor['score']
                if not isinstance(score, str) or not score.isdigit():
                    raise ValueError('Invalid score')
                sides[side] = (team['abbreviation'], int(score))
            home, away = sides['home'], sides['away']
            key = (day.isoformat(), home[0], away[0])
            if key in observed or home[0] == away[0] or home[1] == away[1]:
                raise ValueError('Duplicate or invalid matchup')
            observed[key] = {'espnEventId': event['id'], 'homeScore': home[1], 'awayScore': away[1]}
        days.append(day.isoformat())
        day += timedelta(days=1)
    if not history.season.eq(season).all() or history.duplicated(['gameId', 'team']).any():
        raise ValueError('Invalid NBA history')
    prior = history.loc[pd.to_datetime(history.gameDate).dt.date <= through]
    expected, mappings = set(), []
    registry = {t['abbreviation']: t['id'] for t in teams.get_teams()}
    for game_id, rows in prior.groupby('gameId'):
        if len(rows) != 2 or not rows.isHome.isin([0, 1]).all() or rows.isHome.sum() != 1:
            raise ValueError('NBA game needs two opposite sides')
        home, away = rows.loc[rows.isHome.eq(1)].iloc[0], rows.loc[rows.isHome.eq(0)].iloc[0]
        canonical = dict(season=season, gameId=str(game_id), gameDate=str(home.gameDate),
                         homeTeamId=registry[home.team], awayTeamId=registry[away.team])
        validate_canonical(canonical)
        if home.gameDate != away.gameDate or home.opponent != away.team or away.opponent != home.team:
            raise ValueError('NBA history sides disagree')
        key = (canonical['gameDate'], home.team, away.team)
        if key in expected:
            raise ValueError('Ambiguous NBA matchup mapping')
        expected.add(key)
        result = observed[key]
        margin = result['homeScore'] - result['awayScore']
        if (home.signedMargin != margin or away.signedMargin != -margin or
                home.teamWin != int(margin > 0) or away.teamWin != int(margin < 0)):
            raise ValueError('NBA and ESPN results disagree')
        mappings.append({**canonical, **result})
    if expected != set(observed):
        raise ValueError('ESPN/NBA prior game coverage differs')
    return dict(schemaVersion=1, season=season, seasonType='Regular Season',
                scope='prior-results-cross-check', completeThrough=through.isoformat(),
                checkedAt=datetime.now(timezone.utc).isoformat(), checkedDays=days,
                source=ESPN_SCOREBOARD_URL, games=mappings)


def refresh_coverage(root, season=CURRENT_SEASON, loader=fetch_day, through=None):
    root = Path(root)
    through = through or (datetime.now(ZoneInfo('America/New_York')).date() - timedelta(days=1)).isoformat()
    history = pd.read_csv(root / 'results/season_intelligence' / f'{season}_team_rating_games_v1.csv', dtype={'gameId': str})
    report = verify_coverage(history, season, through, loader)
    destination = root / 'results/live_context' / f'{season}_coverage_v1.json'
    if destination.exists() and json.loads(destination.read_text())['completeThrough'] > through:
        raise ValueError('Refusing coverage regression')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(report, stream, indent=2, allow_nan=False)
            stream.write('\n')
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {'status': 'success', 'completeThrough': through, 'games': len(report['games'])}
