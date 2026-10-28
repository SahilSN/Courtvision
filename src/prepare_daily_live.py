"""Bounded nightly Live preparation, not a viewer-triggered updater or model run."""

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time
from zoneinfo import ZoneInfo
from nba_api.stats.static import teams
from nba_api.stats.library.http import STATS_HEADERS
from espn_live import normalize_name

from daily_live_context import read_day_context
from live_artifacts import digest, read_json, write_json
from live_game_date import eligible_game_date
from official_live_rosters import normalize_roster, roster_url, validate_roster_artifact
from probe_live_access import BASE, fetch_json
from reviewed_live_players import merge_candidates
from season_config import CURRENT_SEASON
from official_profile_lookup import ProfileLookup


def preparation_fetch(url):
    if url.startswith('https://stats.nba.com/stats/commonteamroster?'):
        # Use the official NBA client's normal request identity, while retaining
        # our timeout/size/no-redirect limits. urllib needs uncompressed JSON.
        return fetch_json(url, headers={'User-Agent':STATS_HEADERS['User-Agent'],
            'Referer':'https://www.nba.com/', 'Accept':'application/json', 'Accept-Encoding':'identity'})
    if url.startswith(BASE+'summary?event='):
        return fetch_json(url)
    raise ValueError('Unapproved preparation endpoint')


def summary_sides(payload, game):
    header = payload['header']
    if (str(header['id']) != game['espnEventId'] or header['season']['year'] != int(game['season'][:4])+1
            or header['season']['type'] != 2):
        raise ValueError('Wrong summary identity/season')
    competition, = header['competitions']
    stamp = datetime.fromisoformat(competition['date'].replace('Z','+00:00'))
    if stamp.tzinfo is None or stamp.astimezone(ZoneInfo('America/New_York')).date().isoformat() != game['gameDate']:
        raise ValueError('Wrong summary date')
    registry = {t['id']:t['full_name'] for t in teams.get_teams()}
    sides = {}
    for competitor in competition['competitors']:
        side = competitor['homeAway']
        if side not in ('home','away') or side in sides.values():
            raise ValueError('Ambiguous summary sides')
        team_id = game[side+'TeamId']
        names = {normalize_name(registry[team_id])}
        if team_id == 1610612746:
            names.add(normalize_name('LA Clippers'))
        if normalize_name(competitor['team']['displayName']) not in names:
            raise ValueError('Wrong summary team')
        provider_id = str(competitor['team']['id'])
        if provider_id in sides:
            raise ValueError('Duplicate summary team')
        sides[provider_id] = side
    if len(sides) != 2:
        raise ValueError('Missing summary side')
    return sides


def prepare_daily_live(root, season=CURRENT_SEASON, *, fetcher=preparation_fetch, now=None, budget=65,
                       profile_fetcher=None):
    root = Path(root)
    now = now or datetime.now(timezone.utc)
    directory = root/'results/live_context'
    context_path = directory/f'{season}_day_context_v1.json'
    context = read_json(context_path)
    if (season != CURRENT_SEASON or type(context['schemaVersion']) is not int or context['schemaVersion'] != 1
            or context['season'] != season or context['seasonType'] != 'Regular Season'
            or not eligible_game_date(context['gameDate'], now)
            or context['completeThrough'] != (datetime.fromisoformat(context['gameDate'])-timedelta(days=1)).date().isoformat()
            or not isinstance(context['games'],list)):
        raise ValueError('Current verified day context required')
    games = sorted(context['games'], key=lambda g:(g.get('scheduledAt',''),g['gameId']))
    if len(games) > 15 or len({g['gameId'] for g in games}) != len(games):
        raise ValueError('Invalid daily schedule')
    # Validate the entire published day before HTTP, not only the selected subset.
    for game in games:
        read_day_context(context_path, game)
    selected = games[:4]
    started = time.monotonic()
    try:
        previous = validate_roster_artifact(read_json(directory/f'{season}_roster_identities_v1.json'),
                                            season, context['gameDate'])
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        previous = {'teams': []}
    roster = dict(schemaVersion=1, season=season, seasonType='Regular Season',
                  gameDate=context['gameDate'], checkedAt=now.isoformat(), source='NBA CommonTeamRoster', teams=[])
    selected_teams = {g[side+'TeamId'] for g in selected for side in ('home','away')}
    roster['profiles'] = [p for p in previous.get('profiles', []) if p['teamId'] in selected_teams
        and 0 <= (now-datetime.fromisoformat(p['checkedAt'])).total_seconds() <= 36*3600]
    # Custom/test fetchers never implicitly make external HTTP calls.
    lookup = ProfileLookup(**({'fetcher': profile_fetcher} if profile_fetcher is not None else {}),
                           allowed=lambda: time.monotonic()-started < budget-5)
    use_profiles = fetcher is preparation_fetch or profile_fetcher is not None
    for team_id in sorted({g[side+'TeamId'] for g in selected for side in ('home','away')}):
        team = dict(teamId=team_id, source=roster_url(team_id,season), status='unavailable', players=[])
        try:
            if time.monotonic()-started >= budget:
                raise TimeoutError('Live preparation budget reached')
            payload, _ = fetcher(team['source'])
            team.update(status='verified', players=normalize_roster(payload,team_id,season), checkedAt=now.isoformat())
        except Exception as error:
            # Public IDs and exception classes only; no raw upstream text/payload.
            team['errorType'] = type(error).__name__
            old = next((t for t in previous['teams'] if t['teamId']==team_id and t['status']=='verified'), None)
            if old:
                observed = old.get('checkedAt', previous['checkedAt'])
                age = (now - datetime.fromisoformat(observed)).total_seconds()
                if 0 <= age <= 36*3600:
                    team = {**old, 'checkedAt': observed, 'lastFetchErrorType': type(error).__name__}
        roster['teams'].append(team)
    validate_roster_artifact(roster, season, context['gameDate'])
    roster_path = directory/f'{season}_roster_identities_v1.json'
    pending, observations = {}, []
    for game in selected:
        observation = dict(gameId=game['gameId'], status='unavailable')
        try:
            if time.monotonic()-started >= budget:
                raise TimeoutError('Live preparation budget reached')
            payload, _ = fetcher(BASE+'summary?event='+game['espnEventId'])
            # This collection supplies a REVIEW queue only; never certifies a
            # feed or creates player IDs from ESPN. Match both exact team sides.
            sides = summary_sides(payload,game)
            groups = payload.get('boxscore',{}).get('players',[])
            if not isinstance(groups,list) or len(groups)!=2:
                raise ValueError('Complete summary rosters are not published yet')
            for group in groups:
                team_id = game[sides[str(group['team']['id'])]+'TeamId']
                official = {p['fullName']:p['personId'] for t in roster['teams']
                            if t['teamId'] == team_id for p in t['players']}
                if len(group['statistics']) != 1:
                    raise ValueError('Ambiguous summary statistics')
                for stats in group['statistics']:
                    if not 1 <= len(stats['athletes']) <= 30:
                        raise ValueError('Oversized team roster')
                    for row in stats['athletes']:
                        name = row['athlete']['displayName']
                        if not isinstance(name,str) or not 1 <= len(name) <= 100 or any(ord(c)<32 for c in name):
                            raise ValueError('Invalid public athlete name')
                        # Merge exact official roster evidence with existing
                        # scoped/static identities; disagreement needs review.
                        official_ids = {person for full,person in official.items() if normalize_name(full)==normalize_name(name)}
                        official_ids.update(p['personId'] for p in roster['profiles']
                            if p['teamId']==team_id and normalize_name(p['fullName'])==normalize_name(name))
                        ids = merge_candidates(name,season,team_id,official_ids)
                        profile_error = None
                        if not ids and use_profiles:
                            try:
                                evidence = lookup.resolve(name, team_id, str(row['athlete']['id']), now)
                                roster['profiles'].append(evidence)
                                ids = merge_candidates(name,season,team_id,{evidence['personId']})
                            except Exception as error:
                                profile_error = type(error).__name__
                        if len(ids) != 1:
                            key = (team_id,name)
                            pending[key] = dict(teamId=team_id, fullName=name,
                                                reason='unresolved' if not ids else 'conflicting_identity')
                            if profile_error:
                                pending[key]['profileErrorType'] = profile_error
            observation['status'] = 'inspected'
        except Exception as error:
            observation['errorType'] = type(error).__name__
        observations.append(observation)
    validate_roster_artifact(roster, season, context['gameDate'])
    write_json(roster_path, roster)
    review = dict(schemaVersion=1, season=season, gameDate=context['gameDate'],
                  checkedAt=now.isoformat(), scope='nightly-summary-roster-review-not-full-game-coverage',
                  pending=list(pending.values()), games=observations)
    write_json(directory/f'{season}_identity_review_v1.json', review)
    end = datetime.fromisoformat(context['gameDate']).replace(tzinfo=ZoneInfo('America/New_York')) + timedelta(days=1,hours=6)
    expires = min(end.astimezone(timezone.utc), now+timedelta(hours=24))
    if expires <= now:
        raise ValueError('Daily context window expired')
    manifest = dict(schemaVersion=1, season=season, seasonType='Regular Season',
                    gameDate=context['gameDate'], issuedAt=now.isoformat(), expiresAt=expires.isoformat(),
                    contextDigest=digest(context), gameIds=[g['gameId'] for g in selected],
                    scheduledGames=len(games), deferredGames=max(0,len(games)-4),
                    rosterTeamsVerified=sum(t['status']=='verified' for t in roster['teams']),
                    rosterTeamsUnavailable=sum(t['status']!='verified' for t in roster['teams']),
                    pendingIdentities=len(pending), summaryInspections=observations,
                    scope='prepared-matchups-not-feed-readiness-or-release-certification')
    # Manifest is the last atomic write. A partial/mixed context publication
    # cannot become active because the reader rechecks its exact digest.
    write_json(directory/f'{season}_daily_live_v1.json', manifest)
    return dict(status='prepared' if not pending and all(t['status']=='verified' for t in roster['teams'])
                and all(o['status']=='inspected' for o in observations) else 'degraded',
                gameDate=context['gameDate'], games=len(selected), deferredGames=manifest['deferredGames'],
                pendingIdentities=len(pending), rosterTeamsUnavailable=manifest['rosterTeamsUnavailable'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(prepare_daily_live(args.root),indent=2))


if __name__ == '__main__':
    main()
