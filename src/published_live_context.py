"""Inactive offline publication contract; no feed fetching or application wiring."""

import argparse
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import tempfile

import pandas as pd
from nba_api.stats.static import teams

from cloud_espn_adapter import ProviderContextUnavailable, validate_canonical, verified_pregame_context


def build_context_bundle(source):
    """Require an operator-verified full schedule, independent of completed results.

    This validates an assertion, not the external truth of schedule completeness.
    Rescheduled games must carry their updated date; unresolved earlier games block.
    """
    try:
        if source['schemaVersion'] != 1 or source['seasonType'] != 'Regular Season':
            raise ValueError('Wrong schema or season type')
        season = source['season']
        verification = source['scheduleVerification']
        if verification['scope'] != 'full-season' or verification['verified'] is not True:
            raise ValueError('Full-season verification required')
        for key in ('scheduleSource', 'resultsSource'):
            if not isinstance(source[key], str) or not source[key].strip():
                raise ValueError('Source provenance required')
        checked = datetime.fromisoformat(verification['checkedAt'].replace('Z', '+00:00'))
        if checked.tzinfo is None:
            raise ValueError('Verification timezone required')
        through = date.fromisoformat(source['completeThrough'])
        if through > checked.date():
            raise ValueError('Coverage cannot extend beyond verification')
        registry = {t['id']: t['abbreviation'] for t in teams.get_teams()}
        schedule = source['schedule']
        if not schedule:
            raise ValueError('Empty schedule cannot establish coverage')
        indexed = {}
        for game in schedule:
            validate_canonical(game)
            if game['season'] != season or game['seasonType'] != 'Regular Season':
                raise ValueError('Mixed schedule season')
            if game['gameId'] in indexed:
                raise ValueError('Duplicate scheduled game')
            if any(type(game[f'{side}TeamId']) is not int or game[f'{side}TeamId'] not in registry for side in ('home', 'away')):
                raise ValueError('Unknown canonical team')
            indexed[game['gameId']] = game
        history, completed = [], set()
        for result in source['results']:
            game = indexed[result['gameId']]
            if result['gameId'] in completed:
                raise ValueError('Duplicate result')
            if any(result[key] != game[key] for key in ('season', 'gameDate', 'homeTeamId', 'awayTeamId')):
                raise ValueError('Result/catalog mismatch')
            if result['seasonType'] != 'Regular Season' or result['final'] is not True:
                raise ValueError('Only final regular-season results allowed')
            scores = [result['homeScore'], result['awayScore']]
            if any(type(s) is not int or s < 0 for s in scores) or scores[0] == scores[1]:
                raise ValueError('Invalid final score')
            completed.add(result['gameId'])
            for side in ('home', 'away'):
                history.append({'season': season, 'gameId': game['gameId'], 'gameDate': game['gameDate'],
                                'team': registry[game[f'{side}TeamId']],
                                'teamWin': int((scores[0] > scores[1]) == (side == 'home'))})
        required = {g['gameId'] for g in schedule if date.fromisoformat(g['gameDate']) <= through}
        if not required.issubset(completed):
            raise ValueError('Scheduled prior games lack final results')
        frame = pd.DataFrame(history, columns=['season', 'gameId', 'gameDate', 'team', 'teamWin'])
        contexts = {}
        for game in schedule:
            if date.fromisoformat(game['gameDate']) == through + timedelta(days=1):
                contexts[game['gameId']] = verified_pregame_context(game, frame, pd.DataFrame(schedule),
                    complete_through=through.isoformat(), history_season_type='Regular Season')
        return {'schemaVersion': 1, 'season': season, 'seasonType': 'Regular Season',
                'completeThrough': through.isoformat(), 'scheduleVerification': verification,
                'scheduleSource': source['scheduleSource'], 'resultsSource': source['resultsSource'],
                'schedule': schedule, 'history': history, 'pregameContexts': contexts}
    except (KeyError, ValueError, TypeError, IndexError) as error:
        raise ProviderContextUnavailable(f'Context publication refused: {error}') from None


def publish_context(source, destination):
    """Validate before atomic replace; any invalid refresh retains the last artifact."""
    bundle = build_context_bundle(source)
    destination = Path(destination)
    if destination.exists():
        previous = json.loads(destination.read_text())
        if previous['season'] != bundle['season'] or previous['completeThrough'] > bundle['completeThrough']:
            raise ProviderContextUnavailable('Context publication would change season or regress coverage')
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(bundle, allow_nan=False, sort_keys=True, indent=2) + '\n'
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error('Source and output must differ')
    bundle = publish_context(json.loads(args.source.read_text()), args.output)
    print(f"Validated {len(bundle['pregameContexts'])} pregame contexts through {bundle['completeThrough']}")


if __name__ == '__main__':
    main()
