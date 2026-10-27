import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd

from check_live_deployment import check, progression, summarize
from check_live_deployment import probe_progress
from datetime import datetime
from zoneinfo import ZoneInfo
from offline_live_sample import sample_inputs


class DeploymentReadinessTest(unittest.TestCase):
    def test_real_overnight_check_uses_schedule_date_without_replay_override(self):
        instant = datetime.fromisoformat('2026-10-27T00:15:00-04:00')
        _, bundle = sample_inputs()
        game = dict(bundle['games'][0], gameId='0022600127', gameDate='2026-10-26')
        bundle.update(season='2026-27', gameDate='2026-10-26', games=[game])
        timeline = pd.DataFrame([dict(elapsedGameTime=2400, actionNumber=400, scoreHome=90, scoreAway=100)])
        result = SimpleNamespace(snapshot=SimpleNamespace(timeline=timeline, is_stale=False), predictions=timeline)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'day.json'; path.write_text(json.dumps(bundle))
            fetcher = Mock(return_value=({}, {}))
            with patch('check_live_deployment.datetime') as clock, \
                 patch('check_live_deployment.read_day_context'), \
                 patch('check_live_deployment.current_event', return_value={
                     'competitions':[{'status':{'type':{'state':'in'}}}]}), \
                 patch('check_live_deployment.analyze_live_snapshot', return_value=result) as analyze:
                clock.now.return_value = instant
                report = check([game['gameId']], path, fetcher=fetcher, sleeper=Mock(),
                               artifacts_loader=Mock(), runtime_check=lambda root:True)
                self.assertEqual(report['gameDate'], '2026-10-26')
                self.assertTrue(all('dates=20261026' in call.args[0] for call in fetcher.call_args_list))
                self.assertIsNone(analyze.call_args.kwargs['as_of_date'])
                fetcher.reset_mock()
                clock.now.return_value = instant.replace(hour=6)
                with self.assertRaises(ValueError):
                    check([game['gameId']], path, fetcher=fetcher, artifacts_loader=Mock())
                fetcher.assert_not_called()

    def test_operator_measurement_never_injects_controlled_fixtures(self):
        day = json.loads((Path(__file__).resolve().parents[1]/'results/live_context/2026-27_day_context_v1.json').read_text())['gameDate']
        with patch('check_live_deployment.check', return_value={'status':'not_ready'}) as checked, \
             patch('check_live_deployment.eligible_game_date', return_value=True), \
             patch('live_release_recovery.verify_recovery') as controlled:
            report = probe_progress(day, 'community-cloud', ['0022600127'])
        controlled.assert_not_called()
        self.assertEqual(checked.call_args.kwargs['rounds_count'], 3)
        self.assertEqual(report['controlledRecovery']['status'], 'not_run')

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

    def test_recovered_feed_needs_two_consecutive_valid_final_observations(self):
        good = dict(gameId='0022600127', status='validated', sourceState='in', elapsed=10, action=5)
        bad = dict(gameId='0022600127', status='failed')
        newer = dict(good, elapsed=11)
        self.assertEqual(summarize([[bad], [good], [newer]], ['0022600127'])['status'], 'current_feed_passed')
        for rounds in ([[good], [newer], [bad]], [[good], [bad], [newer]], [[bad], [good], [good]]):
            self.assertEqual(summarize(rounds, ['0022600127'])['status'], 'not_ready')
        for count in (1, 4, True):
            with self.assertRaises(ValueError):
                check(['0022600127'], '/missing', rounds_count=count)

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
                pairs = {}
                accepted = iter([result(10), result(11, stale)])
                feeds = [{'marker': 'first'}, {'marker': 'second'}]
                def analyze(*args, **kwargs):
                    args[3]()
                    return next(accepted)
                with patch('check_live_deployment.read_day_context'), \
                     patch('check_live_deployment.current_event', return_value={
                         'competitions':[{'status':{'type':{'state':'in'}}}]}), \
                     patch('check_live_deployment.summary_pair', side_effect=feeds), \
                     patch('check_live_deployment.analyze_live_snapshot', side_effect=analyze):
                    report = check([game['gameId']], path, today=bundle['gameDate'],
                        fetcher=fetcher, sleeper=sleeper, artifacts_loader=Mock(),
                        runtime_check=lambda root:True, verified_pairs=pairs)
                self.assertEqual(report['status'], 'not_ready' if stale else 'current_feed_passed')
                self.assertFalse(report['canEnableLive'])
                self.assertEqual(fetcher.call_count, 2)
                sleeper.assert_called_once_with(16)
                self.assertEqual(pairs[game['gameId']]['marker'], 'first' if stale else 'second')
                pairs[game['gameId']]['marker'] = 'changed'
                self.assertEqual(feeds[0]['marker'], 'first')
                self.assertEqual(feeds[1]['marker'], 'second')
