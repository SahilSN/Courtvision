"""Inactive display-only ESPN traditional box adapter; no inferred advanced stats."""

import re
import pandas as pd

from cloud_espn_adapter import normalize_snapshot, ProviderContextUnavailable, ScoreSectionsUnreconciled
from reviewed_live_players import candidates


COUNTS = {'PTS': 'points', 'REB': 'reboundsTotal', 'AST': 'assists', 'TO': 'turnovers',
          'STL': 'steals', 'BLK': 'blocks', 'OREB': 'reboundsOffensive',
          'DREB': 'reboundsDefensive', 'PF': 'foulsPersonal'}
SHOTS = {'FG': 'fieldGoals', '3PT': 'threePointers', 'FT': 'freeThrows'}


def normalize_box(event, summary, canonical):
    return _normalize_box(event, summary, canonical)


def _normalize_box(event, summary, canonical, timeline=None):
    try:
        # Reuse strict game/date/team/timeline validation. One caller-owned JSON
        # snapshot supplies both panels; this never performs another HTTP request.
        if timeline is None:
            timeline = normalize_snapshot(event, summary, canonical)
        sides = {str(c['team']['id']): c['homeAway'] for c in summary['header']['competitions'][0]['competitors']}
        # Live display only: providers can mark a player as participating before
        # publishing minutes. Preserve missingness, never infer zero or DNP.
        in_progress = summary['header']['competitions'][0]['status']['type'].get('state') == 'in'
        rows, totals, seen, seen_teams, seen_people = [], [], set(), set(), set()
        for group in summary['boxscore']['players']:
            provider_team = str(group['team']['id'])
            if provider_team in seen_teams:
                raise ValueError('Duplicate team')
            seen_teams.add(provider_team)
            side = sides[provider_team]
            team_id = canonical[side + 'TeamId']
            stats, = group['statistics']
            labels = stats['labels']
            if len(set(labels)) != len(labels) or not (set(COUNTS) | set(SHOTS) | {'MIN', '+/-'}).issubset(labels):
                raise ValueError('Missing or ambiguous stat labels')
            team_points = 0
            for athlete in stats['athletes']:
                person = athlete['athlete']
                key = str(person['id'])
                if key in seen:
                    raise ValueError('Duplicate athlete')
                seen.add(key)
                if type(athlete['didNotPlay']) is not bool:
                    raise ValueError('Unknown participation')
                matches = candidates(person['displayName'],canonical['season'],team_id,canonical['gameDate'])
                played = not athlete['didNotPlay']
                if played and len(matches) != 1:
                    raise ValueError('Unresolved participating player')
                if len(matches) == 1:
                    person_id = next(iter(matches))
                    if person_id in seen_people:
                        raise ValueError('Conflicting canonical athlete identity')
                    seen_people.add(person_id)
                row = dict(gameId=canonical['gameId'], teamId=team_id,
                           personId=next(iter(matches)) if len(matches) == 1 else None,
                           espnAthleteId=key, fullName=person['displayName'],
                           starter=athlete['starter'], didNotPlay=not played,
                           comment=athlete.get('reason', '') if not played else '')
                if played:
                    if len(athlete['stats']) != len(labels):
                        raise ValueError('Truncated player stats')
                    values = dict(zip(labels, athlete['stats']))
                    for label, column in COUNTS.items():
                        if not re.fullmatch(r'\d+', values[label]):
                            raise ValueError('Invalid count')
                        row[column] = int(values[label])
                    for label, prefix in SHOTS.items():
                        match = re.fullmatch(r'(\d+)-(\d+)', values[label])
                        if match is None:
                            raise ValueError('Invalid shooting stat')
                        made, attempted = map(int, match.groups())
                        if made > attempted:
                            raise ValueError('Shooting makes exceed attempts')
                        row[prefix + 'Made'], row[prefix + 'Attempted'] = made, attempted
                    if (row['points'] != 2*row['fieldGoalsMade'] + row['threePointersMade'] + row['freeThrowsMade'] or
                            row['threePointersMade'] > row['fieldGoalsMade'] or
                            row['threePointersAttempted'] > row['fieldGoalsAttempted'] or
                            row['reboundsTotal'] != row['reboundsOffensive'] + row['reboundsDefensive']):
                        raise ValueError('Inconsistent player totals')
                    minutes_missing = in_progress and values['MIN'] in ('-', '--')
                    if (not minutes_missing and not re.fullmatch(r'\d+(?::[0-5]\d)?', values['MIN'])) or not re.fullmatch(r'[+-]?\d+', values['+/-']):
                        raise ValueError('Invalid minutes or plus/minus')
                    row['minutesDisplay'] = None if minutes_missing else values['MIN']
                    row['minutesAvailable'] = not minutes_missing
                    row['plusMinusPoints'] = int(values['+/-'])
                    team_points += row['points']
                rows.append(row)
            if len(stats['totals']) != len(labels):
                raise ValueError('Missing team totals')
            reported = dict(zip(labels, stats['totals']))['PTS']
            if not re.fullmatch(r'\d+', reported):
                raise ValueError('Invalid team points')
            if int(reported) != team_points or team_points != int(timeline['scoreHome' if side == 'home' else 'scoreAway'].iloc[-1]):
                raise ScoreSectionsUnreconciled('Player/team/header points disagree')
            totals.append(dict(teamId=team_id, points=team_points))
        if seen_teams != set(sides):
            raise ValueError('Missing box-score team')
        return {'players': pd.DataFrame(rows), 'teams': pd.DataFrame(totals),
                'source': 'ESPN', 'advancedStatsAvailable': False}
    except ScoreSectionsUnreconciled:
        raise
    except (KeyError, ValueError, TypeError, IndexError) as error:
        raise ProviderContextUnavailable('ESPN box score unavailable or unreconciled') from error
