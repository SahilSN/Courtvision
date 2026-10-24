from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from cloud_espn_adapter import ProviderContextUnavailable
from published_live_context import build_context_bundle, publish_context


class PublishedContextTest(unittest.TestCase):
    def setUp(self):
        self.prior = dict(season='2026-27', seasonType='Regular Season', gameId='0022600001',
                          gameDate='2026-10-21', homeTeamId=1610612760, awayTeamId=1610612745)
        self.target = {**self.prior, 'gameId': '0022600002', 'gameDate': '2026-10-22'}
        self.source = dict(schemaVersion=1, season='2026-27', seasonType='Regular Season',
            completeThrough='2026-10-21', scheduleSource='synthetic independent schedule',
            resultsSource='synthetic final results',
            scheduleVerification=dict(scope='full-season', verified=True, checkedAt='2026-10-22T10:00:00Z'),
            schedule=[self.prior, self.target],
            results=[{**self.prior, 'final': True, 'homeScore': 101, 'awayScore': 99}])

    def test_raw_record_and_unchanged_smoothing(self):
        result = build_context_bundle(self.source)['pregameContexts'][self.target['gameId']]
        self.assertEqual(result['homePreGameWins'], 1)
        self.assertEqual(result['awayPreGameLosses'], 1)
        self.assertAlmostEqual(result['homePreGameWinPct'], 2 / 3)

    def test_missing_results_fail_not_neutral(self):
        self.source['results'] = []
        with self.assertRaises(ProviderContextUnavailable):
            build_context_bundle(self.source)

    def test_empty_opening_night_is_verified_not_inferred(self):
        self.source.update(completeThrough='2026-10-20', schedule=[self.prior], results=[])
        result = build_context_bundle(self.source)['pregameContexts'][self.prior['gameId']]
        self.assertEqual(result['homePreGameWinPct'], 0.5)

    def test_bad_provenance_or_incomplete_schedule_rejected(self):
        for field, value in [('verified', False), ('scope', 'completed-only'), ('checkedAt', '2026-10-20T00:00:00Z')]:
            source = deepcopy(self.source)
            source['scheduleVerification'][field] = value
            with self.subTest(field=field), self.assertRaises(ProviderContextUnavailable):
                build_context_bundle(source)

    def test_mismatches_preseason_duplicate_and_bad_scores_rejected(self):
        for field, value in [('gameDate', '2026-10-20'), ('homeTeamId', 1610612747),
                             ('seasonType', 'Pre Season'), ('final', False), ('homeScore', True), ('awayScore', 101)]:
            source = deepcopy(self.source)
            source['results'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ProviderContextUnavailable):
                build_context_bundle(source)
        for key in ('schedule', 'results'):
            source = deepcopy(self.source)
            source[key].append(deepcopy(source[key][0]))
            with self.assertRaises(ProviderContextUnavailable):
                build_context_bundle(source)

    def test_target_day_result_does_not_leak(self):
        self.source['results'].append({**self.target, 'final': True, 'homeScore': 80, 'awayScore': 90})
        context = build_context_bundle(self.source)['pregameContexts'][self.target['gameId']]
        self.assertEqual(context['homePreGameLosses'], 0)

    def test_atomic_publication_preserves_valid_artifact_on_failed_refresh(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'context.json'
            publish_context(self.source, destination)
            before = destination.read_bytes()
            self.source['results'] = []
            with self.assertRaises(ProviderContextUnavailable):
                publish_context(self.source, destination)
            self.assertEqual(destination.read_bytes(), before)
            self.assertEqual(json.loads(before)['schemaVersion'], 1)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)

    def test_coverage_regression_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'context.json'
            publish_context(self.source, destination)
            self.source['completeThrough'] = '2026-10-20'
            with self.assertRaises(ProviderContextUnavailable):
                publish_context(self.source, destination)
