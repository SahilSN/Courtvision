from copy import deepcopy
import json
from pathlib import Path
import unittest
import pandas as pd
from unittest.mock import patch

from cloud_espn_box import normalize_box
from cloud_espn_adapter import ProviderContextUnavailable


class BoxAdapterTest(unittest.TestCase):
    def setUp(self):
        directory = Path(__file__).parent / 'fixtures'
        self.feed = json.loads((directory/'espn_contract_0022500001.json').read_text())
        self.feed['summary']['boxscore']['players'] = json.loads((directory/'espn_box_0022500001.json').read_text())['players']

    def normalize(self):
        with patch('requests.sessions.Session.request', side_effect=AssertionError('Unexpected network')):
            return normalize_box(self.feed['event'], self.feed['summary'], self.feed['canonical'])

    def test_captured_box_reconciles_and_has_no_advanced_fabrication(self):
        result = self.normalize()
        self.assertEqual(sorted(result['teams'].points), [124,125])
        self.assertFalse(result['advancedStatsAvailable'])
        self.assertNotIn('possessions', result['players'])
        self.assertFalse(result['players'].duplicated('espnAthleteId').any())
        dnp = result['players'].loc[result['players'].didNotPlay]
        self.assertTrue(dnp.points.isna().all())

    def test_reordered_labels_supported(self):
        baseline = self.normalize()['players'].points
        for group in self.feed['summary']['boxscore']['players']:
            stats = group['statistics'][0]
            stats['labels'].reverse(); stats['totals'].reverse()
            for athlete in stats['athletes']: athlete['stats'].reverse()
        pd.testing.assert_series_equal(self.normalize()['players'].points,baseline)

    def test_missing_malformed_duplicate_or_unreconciled_refused(self):
        original = deepcopy(self.feed)
        for defect in ('missing','count','shooting','duplicate','unknown','total','team','minutes'):
            self.feed = deepcopy(original)
            group = self.feed['summary']['boxscore']['players'][0]
            stats = group['statistics'][0]
            athlete = stats['athletes'][0]
            if defect == 'missing': athlete['stats'].pop()
            if defect == 'count': athlete['stats'][stats['labels'].index('PTS')] = '--'
            if defect == 'shooting': athlete['stats'][stats['labels'].index('FG')] = '99-1'
            if defect == 'duplicate': stats['athletes'].append(deepcopy(athlete))
            if defect == 'unknown': athlete['athlete']['displayName'] = 'Unresolved Player'
            if defect == 'total': stats['totals'][stats['labels'].index('PTS')] = '999'
            if defect == 'team': self.feed['summary']['boxscore']['players'].pop()
            if defect == 'minutes': athlete['stats'][stats['labels'].index('MIN')] = '--'
            with self.subTest(defect=defect), self.assertRaises(ProviderContextUnavailable): self.normalize()

    def test_played_zero_minutes_not_reclassified_as_dnp(self):
        athlete = self.feed['summary']['boxscore']['players'][0]['statistics'][0]['athletes'][0]
        athlete['stats'][0] = '0'
        result = self.normalize()['players'].iloc[0]
        self.assertFalse(result.didNotPlay)
        self.assertEqual(result.minutesDisplay,'0')

    def test_wrong_canonical_game_refused(self):
        self.feed['canonical']['gameDate'] = '2025-10-22'
        with self.assertRaises(ProviderContextUnavailable): self.normalize()
