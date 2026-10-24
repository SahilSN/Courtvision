"""Publish verified day identities and read strictly dated pregame context offline."""

from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo

import pandas as pd
from nba_api.stats.static import teams

from cloud_espn_adapter import ProviderContextUnavailable, validate_canonical, verified_pregame_context
from espn_live import normalize_name
from espn_record_coverage import fetch_day, refresh_coverage
from game_catalog import fetch_games_for_date_from_scoreboard
from live_analysis import apply_current_season_pregame_smoothing
from season_config import CURRENT_SEASON


def build_day_context(nba_games, espn, coverage, season, game_date):
    day = date.fromisoformat(game_date)
    through = day - timedelta(days=1)
    if (coverage['schemaVersion'] != 1 or coverage['season'] != season or
            coverage['seasonType'] != 'Regular Season' or coverage['scope'] != 'prior-results-cross-check' or
            coverage['completeThrough'] != through.isoformat()):
        raise ProviderContextUnavailable('Prior coverage is not valid for this game date')
    days = [date.fromisoformat(value) for value in coverage['checkedDays']]
    if not days or days[-1] != through or days != [days[0] + timedelta(days=i) for i in range(len(days))]:
        raise ProviderContextUnavailable('Daily coverage has gaps')
    registry = {t['id']: t for t in teams.get_teams()}
    names = {normalize_name(t['full_name']): t['id'] for t in registry.values()}
    names[normalize_name('LA Clippers')] = 1610612746
    league = espn['leagues'][0]
    if league['id'] != '46' or league['season']['year'] != int(season[:4]) + 1:
        raise ProviderContextUnavailable('Wrong scoreboard season')
    by_matchup, event_ids = {}, set()
    for event in espn['events']:
        if event['season']['year'] != int(season[:4]) + 1:
            raise ProviderContextUnavailable('Wrong event season')
        if event['season']['type'] != 2:
            continue
        competition, = event['competitions']
        timestamp = datetime.fromisoformat(competition['date'].replace('Z', '+00:00'))
        if timestamp.tzinfo is None or timestamp.astimezone(ZoneInfo('America/New_York')).date() != day:
            raise ProviderContextUnavailable('Wrong event date')
        sides = {}
        for competitor in competition['competitors']:
            side = competitor['homeAway']
            if side not in ('home', 'away') or side in sides:
                raise ProviderContextUnavailable('Ambiguous sides')
            sides[side] = names[normalize_name(competitor['team']['displayName'])]
        key = (sides['home'], sides['away'])
        if len(sides) != 2 or key in by_matchup or event['id'] in event_ids:
            raise ProviderContextUnavailable('Ambiguous ESPN identity')
        by_matchup[key] = str(event['id'])
        event_ids.add(event['id'])
    schedule, history, seen_ids = [], [], set()
    for prior in coverage['games']:
        validate_canonical(prior)
        if (prior['season'] != season or not days[0] <= date.fromisoformat(prior['gameDate']) <= through
                or prior['gameId'] in seen_ids):
            raise ProviderContextUnavailable('Invalid prior game coverage')
        seen_ids.add(prior['gameId'])
        scores = (prior['homeScore'], prior['awayScore'])
        if any(type(s) is not int or s < 0 for s in scores) or scores[0] == scores[1]:
            raise ProviderContextUnavailable('Invalid final score')
        schedule.append({**prior, 'seasonType': 'Regular Season'})
        for side in ('home', 'away'):
            history.append(dict(season=season, gameId=prior['gameId'], gameDate=prior['gameDate'],
                team=registry[prior[side + 'TeamId']]['abbreviation'],
                teamWin=int((scores[0] > scores[1]) == (side == 'home'))))
    mapped, expected = [], set()
    for nba in nba_games:
        canonical = dict(season=season, gameDate=nba['game_date'], gameId=nba['game_id'],
                         homeTeamId=nba['home_team_id'], awayTeamId=nba['away_team_id'])
        validate_canonical(canonical)
        key = (canonical['homeTeamId'], canonical['awayTeamId'])
        if canonical['gameDate'] != game_date or key in expected or canonical['gameId'] in seen_ids:
            raise ProviderContextUnavailable('Ambiguous NBA day identity')
        expected.add(key)
        seen_ids.add(canonical['gameId'])
        mapped.append({**canonical, 'espnEventId': by_matchup[key]})
        schedule.append({**canonical, 'seasonType': 'Regular Season'})
    if expected != set(by_matchup):
        raise ProviderContextUnavailable('NBA/ESPN daily game sets disagree')
    frame = pd.DataFrame(history, columns=['season', 'gameDate', 'gameId', 'team', 'teamWin'])
    for game in mapped:
        game['pregameContext'] = verified_pregame_context(game, frame, pd.DataFrame(schedule),
            complete_through=through.isoformat(), history_season_type='Regular Season')
    return dict(schemaVersion=1, season=season, seasonType='Regular Season', gameDate=game_date,
                completeThrough=through.isoformat(), checkedAt=datetime.now(timezone.utc).isoformat(),
                coverageCheckedAt=coverage['checkedAt'], games=mapped)


def read_day_context(path, canonical):
    """No HTTP, neutral fallback or cross-day reuse. Revalidate caller identity."""
    try:
        validate_canonical(canonical)
        bundle = json.loads(Path(path).read_text())
        if (bundle['schemaVersion'] != 1 or bundle['seasonType'] != 'Regular Season' or
                bundle['season'] != canonical['season'] or bundle['gameDate'] != canonical['gameDate'] or
                bundle['completeThrough'] != (date.fromisoformat(canonical['gameDate']) - timedelta(days=1)).isoformat()):
            raise ProviderContextUnavailable('Stale or wrong dated context')
        matches = [g for g in bundle['games'] if g['gameId'] == canonical['gameId']]
        if len(matches) != 1 or any(matches[0][key] != value for key, value in canonical.items()):
            raise ProviderContextUnavailable('Unknown or mismatched canonical game')
        context = matches[0]['pregameContext']
        if any(context[side + 'TeamId'] != canonical[side + 'TeamId'] for side in ('home', 'away')):
            raise ProviderContextUnavailable('Pregame team identity mismatch')
        recomputed = context.copy()
        for side in ('home', 'away'):
            wins, losses = (context[side + 'PreGame' + field] for field in ('Wins', 'Losses'))
            if any(type(n) is not int or n < 0 for n in (wins, losses)):
                raise ProviderContextUnavailable('Invalid pregame record')
            recomputed[side + 'PreGameWinPct'] = wins / (wins + losses) if wins + losses else 0.5
        recomputed['strengthDifference'] = recomputed['homePreGameWinPct'] - recomputed['awayPreGameWinPct']
        if context != apply_current_season_pregame_smoothing(recomputed, canonical['season'], 'Regular Season'):
            raise ProviderContextUnavailable('Pregame probabilities disagree with raw records')
        return matches[0]
    except (OSError, KeyError, ValueError, TypeError, IndexError) as error:
        raise ProviderContextUnavailable('Dated pregame context unavailable') from error


def refresh_day_context(root, season=CURRENT_SEASON, game_date=None, nba_loader=fetch_games_for_date_from_scoreboard,
                        espn_loader=fetch_day):
    day = date.fromisoformat(game_date) if game_date else datetime.now(ZoneInfo('America/New_York')).date()
    directory = Path(root) / 'results/live_context'
    coverage = json.loads((directory / f'{season}_coverage_v1.json').read_text())
    bundle = build_day_context(nba_loader(day.isoformat(), timeout=8), espn_loader(day), coverage, season, day.isoformat())
    destination = directory / f'{season}_day_context_v1.json'
    if destination.exists() and json.loads(destination.read_text())['gameDate'] > day.isoformat():
        raise ProviderContextUnavailable('Refusing dated context regression')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=directory, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(bundle, stream, indent=2, allow_nan=False)
            stream.write('\n')
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {'status': 'success', 'gameDate': day.isoformat(), 'games': len(bundle['games'])}


def refresh_nightly_context(root):
    coverage = refresh_coverage(root)
    coverage['dayContext'] = refresh_day_context(root)
    return coverage
