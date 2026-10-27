import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd

from check_live_deployment import check, progression, summarize
from offline_live_sample import sample_inputs


class DeploymentReadinessTest(unittest.TestCase):
    def test_only_validated_advancing_in_progress_feed_passes(self):
        first = dict(gameId='0022600120', status='validated', sourceState='in', elapsed=10, action=5)
        self.assertTrue(progression(first, dict(first, elapsed=11)))
        self.assertTrue(progression(first, dict(first, action=6)))
        self.assertTrue(progression(first, dict(first, elapsed=2880, sourceState='post')))
        for second in (first, dict(first, status='stale', elapsed=11),
                       dict(first, status='failed'), dict(first, elapsed=9, action=20)):
            self.assertFalse(progression(first, second))
        self.assertFalse(progression(dict(first, sourceState='post'), dict(first, elapsed=11)))
        report = summarize([[first], [dict(first, elapsed=11)]], ['0022600120'])
        self.assertEqual(report['status'], 'current_feed_passed')
        self.assertFalse(report['canEnableLive'])
        self.assertEqual(summarize([[first], []], ['0022600120'])['status'], 'not_ready')
        self.assertEqual(summarize([], [])['status'], 'not_ready')

    def test_bad_selection_and_context_block_before_http_or_model(self):
        fetcher, artifacts = Mock(), Mock()
        for ids in ([], ['0022600120']*2, ['0022500001'], ['bad'], ['002260012'+str(i) for i in range(5)]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                check(ids, '/missing', fetcher=fetcher, artifacts_loader=artifacts)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'day.json'
            path.write_text(json.dumps({'gameDate': '2026-10-25'}))
            with self.assertRaises(ValueError):
                check(['0022600120'], path, today='2026-10-26', fetcher=fetcher, artifacts_loader=artifacts)
        fetcher.assert_not_called(); artifacts.assert_not_called()

    def test_runtime_block_never_fetches_or_loads_model(self):
        _, bundle = sample_inputs()
        game = dict(bundle['games'][0], gameId='0022600120')
        bundle['season'] = '2026-27'
        bundle['games'] = [game]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'day.json'; path.write_text(json.dumps(bundle))
            fetcher, artifacts = Mock(), Mock()
            with patch('check_live_deployment.read_day_context'):
                report = check([game['gameId']], path, today=bundle['gameDate'],
                    fetcher=fetcher, artifacts_loader=artifacts, runtime_check=lambda root:False)
            self.assertEqual(report['status'], 'runtime_blocked')
            fetcher.assert_not_called(); artifacts.assert_not_called()

    def test_two_round_pipeline_is_bounded_and_stale_never_passes(self):
        _, bundle = sample_inputs()
        game = dict(bundle['games'][0], gameId='0022600120')
        bundle.update(season='2026-27', games=[game])
        def result(elapsed, stale=False):
            timeline = pd.DataFrame([dict(elapsedGameTime=elapsed, actionNumber=2,
                                         scoreHome=10, scoreAway=9)])
            return SimpleNamespace(snapshot=SimpleNamespace(timeline=timeline, is_stale=stale),
                                   predictions=timeline)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'day.json'; path.write_text(json.dumps(bundle))
            for stale in (False, True):
                fetcher, sleeper = Mock(return_value=({}, {})), Mock()
                with patch('check_live_deployment.read_day_context'), \
                     patch('check_live_deployment.current_event', return_value={
                         'competitions':[{'status':{'type':{'state':'in'}}}]}), \
                     patch('check_live_deployment.analyze_live_snapshot',
                           side_effect=[result(10), result(11, stale)]):
                    report = check([game['gameId']], path, today=bundle['gameDate'],
                        fetcher=fetcher, sleeper=sleeper, artifacts_loader=Mock(),
                        runtime_check=lambda root:True)
                self.assertEqual(report['status'], 'not_ready' if stale else 'current_feed_passed')
                self.assertFalse(report['canEnableLive'])
                self.assertEqual(fetcher.call_count, 2)
                sleeper.assert_called_once_with(16)
