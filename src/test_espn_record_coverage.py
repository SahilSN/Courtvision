from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

import pandas as pd

from espn_record_coverage import refresh_coverage, verify_coverage


class CoverageTest(unittest.TestCase):
    def setUp(self):
        self.payload = {'leagues': [{'id': '46', 'season': {'year': 2027,
            'displayName': '2026-27', 'startDate': '2026-10-20T07:00Z'}}], 'events': [{
            'id': 'espn-1', 'season': {'year': 2027, 'type': 2}, 'competitions': [{
                'date': '2026-10-20T23:00Z', 'status': {'type': {'completed': True}},
                'competitors': [
                    {'homeAway': 'home', 'team': {'displayName': 'Oklahoma City Thunder'}, 'score': '105'},
                    {'homeAway': 'away', 'team': {'displayName': 'Houston Rockets'}, 'score': '100'}]}]}]}
        self.history = pd.DataFrame([
            dict(season='2026-27', gameId='0022600001', gameDate='2026-10-20', team='OKC', opponent='HOU', isHome=1, teamWin=1, signedMargin=5),
            dict(season='2026-27', gameId='0022600001', gameDate='2026-10-20', team='HOU', opponent='OKC', isHome=0, teamWin=0, signedMargin=-5)])

    def verify(self, payload=None, history=None):
        return verify_coverage(self.history if history is None else history, '2026-27', '2026-10-20',
                               loader=Mock(return_value=payload or self.payload))

    def test_crosswalk_preserves_independent_nba_id(self):
        result = self.verify()
        self.assertEqual(result['games'][0]['gameId'], '0022600001')
        self.assertEqual(result['games'][0]['espnEventId'], 'espn-1')
        self.assertEqual(result['checkedDays'], ['2026-10-20'])

    def test_missing_either_source_fails(self):
        payload = deepcopy(self.payload)
        payload['events'] = []
        with self.assertRaises((KeyError, ValueError)):
            self.verify(payload)
        with self.assertRaises(ValueError):
            self.verify(history=self.history.iloc[:0])

    def test_score_mismatch_and_bad_history_sides_fail(self):
        for field, value in [('signedMargin', 6), ('isHome', 0), ('teamWin', 0), ('opponent', 'LAL')]:
            history = self.history.copy()
            history.loc[0, field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.verify(history=history)

    def test_wrong_season_duplicate_unknown_team_unfinished_fail(self):
        for defect in ('season', 'duplicate', 'team', 'unfinished', 'date'):
            payload = deepcopy(self.payload)
            event = payload['events'][0]
            if defect == 'season': event['season']['year'] = 2026
            if defect == 'duplicate': payload['events'].append(deepcopy(event))
            if defect == 'team': event['competitions'][0]['competitors'][0]['team']['displayName'] = 'Unknown'
            if defect == 'unfinished': event['competitions'][0]['status']['type']['completed'] = False
            if defect == 'date': event['competitions'][0]['date'] = '2026-10-21T23:00Z'
            with self.subTest(defect=defect), self.assertRaises((KeyError, ValueError)):
                self.verify(payload)

    def test_every_day_queried_including_empty_days(self):
        empty = deepcopy(self.payload)
        empty['events'] = []
        loader = Mock(side_effect=[empty, self.payload])
        result = verify_coverage(self.history, '2026-27', '2026-10-21', loader)
        self.assertEqual(result['checkedDays'], ['2026-10-20', '2026-10-21'])
        self.assertEqual(loader.call_count, 2)

    def test_timeout_does_not_publish_or_replace_last_good_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            history = root / 'results/season_intelligence/2026-27_team_rating_games_v1.csv'
            history.parent.mkdir(parents=True)
            self.history.to_csv(history, index=False)
            refresh_coverage(root, loader=Mock(return_value=self.payload), through='2026-10-20')
            path = root / 'results/live_context/2026-27_coverage_v1.json'
            before = path.read_bytes()
            with self.assertRaises(TimeoutError):
                refresh_coverage(root, loader=Mock(side_effect=TimeoutError()), through='2026-10-21')
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(json.loads(before)['completeThrough'], '2026-10-20')
