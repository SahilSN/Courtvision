from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import joblib
import torch

from cloud_live_analysis import analyze_live_snapshot
from cloud_espn_adapter import ProviderContextUnavailable
from feature_engineering import MODEL_FEATURES
from model import WinProbabilityMLP
from live_snapshot_cache import LiveSnapshotCache


class AnalysisJoinTest(unittest.TestCase):
    def test_overnight_original_context_and_cutoff(self):
        from datetime import datetime
        with patch('cloud_live_analysis.datetime') as clock:
            clock.now.return_value = datetime.fromisoformat('2025-10-22T00:15:00-04:00')
            result = analyze_live_snapshot(self.cache, self.feed['canonical'], self.path,
                                           self.loader, self.artifacts)
            self.assertTrue(len(result.predictions))
            self.assertEqual(self.day['completeThrough'], '2025-10-20')
            clock.now.return_value = datetime.fromisoformat('2025-10-22T06:00:00-04:00')
            self.loader.reset_mock()
            with self.assertRaises(ProviderContextUnavailable):
                analyze_live_snapshot(self.cache, self.feed['canonical'], self.path,
                                      self.loader, self.artifacts)
            self.loader.assert_not_called()

    def test_overnight_unstarted_game_is_rejected(self):
        from datetime import datetime
        feed = deepcopy(self.feed)
        feed['event']['competitions'][0]['status']['type']['state'] = 'pre'
        self.loader.return_value = feed
        with patch('cloud_live_analysis.datetime') as clock:
            clock.now.return_value = datetime.fromisoformat('2025-10-22T00:15:00-04:00')
            with self.assertRaises(RuntimeError):
                analyze_live_snapshot(self.cache, self.feed['canonical'], self.path,
                                      self.loader, self.artifacts)

    def test_release_interruption_retains_expires_and_recovers_without_data_changes(self):
        from live_release_recovery import verify_recovery
        report = verify_recovery(self.feed['canonical'], self.path, self.feed, self.artifacts)
        self.assertEqual(report['status'], 'passed')
        self.assertTrue(report['expiredUnavailable'])

    @classmethod
    def setUpClass(cls):
        root=Path(__file__).resolve().parents[1]
        cls.feed=json.loads((root/'src/fixtures/espn_contract_0022500001.json').read_text())
        cls.feed['summary']['boxscore']['players']=json.loads((root/'src/fixtures/espn_box_0022500001.json').read_text())['players']
        model=WinProbabilityMLP(input_size=len(MODEL_FEATURES))
        model.load_state_dict(torch.load(root/'models/win_probability_mlp_v7.pt',map_location='cpu',weights_only=True))
        model.eval()
        cls.artifacts=(model,joblib.load(root/'models/win_probability_scaler_v7.pkl'),torch.device('cpu'))

    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.path=Path(temporary.name)/'day.json'
        game=self.feed['canonical']
        context=dict(homeTeamId=game['homeTeamId'],awayTeamId=game['awayTeamId'],homePreGameWins=0,
            homePreGameLosses=0,awayPreGameWins=0,awayPreGameLosses=0,homePreGameWinPct=0.5,awayPreGameWinPct=0.5,strengthDifference=0.0)
        self.day=dict(schemaVersion=1,season=game['season'],seasonType='Regular Season',gameDate=game['gameDate'],completeThrough='2025-10-20',
                      games=[{**game,'espnEventId':self.feed['event']['id'],'pregameContext':context}])
        self.save()
        self.loader=Mock(return_value=self.feed)
        self.clock=Mock(return_value=0)
        self.cache=LiveSnapshotCache(ttl=5,max_age=20,clock=self.clock)
        blocker=patch('requests.sessions.Session.request',side_effect=AssertionError('Unexpected HTTP'))
        blocker.start();self.addCleanup(blocker.stop)

    def save(self): self.path.write_text(json.dumps(self.day))

    def run_join(self, **kwargs):
        return analyze_live_snapshot(self.cache,self.feed['canonical'],self.path,self.loader,self.artifacts,
                                     as_of_date=kwargs.get('as_of_date','2025-10-21'))

    def test_archived_pipeline_uses_frozen_cpu_artifacts_and_joint_box(self):
        result=self.run_join()
        self.assertEqual(len(result.predictions),len(result.snapshot.timeline))
        self.assertTrue(result.predictions.winProbability.between(0,1).all())
        self.assertEqual(result.display_state,'progress_unknown')
        self.assertEqual(sorted(result.snapshot.box['teams'].points),[124,125])
        self.loader.assert_called_once()

    def test_wrong_date_stale_or_corrupt_context_blocks_before_loader(self):
        with self.assertRaises(ProviderContextUnavailable): self.run_join(as_of_date='2025-10-22')
        self.day['completeThrough']='2025-10-19';self.save()
        with self.assertRaises(ProviderContextUnavailable): self.run_join()
        self.path.write_text('{')
        with self.assertRaises(ProviderContextUnavailable): self.run_join()
        self.loader.assert_not_called()

    def test_wrong_espn_mapping_blocks_analysis(self):
        self.day['games'][0]['espnEventId']='wrong';self.save()
        with self.assertRaises(RuntimeError): self.run_join()

    def test_retained_pair_predictions_explicitly_stale(self):
        first=self.run_join()
        self.clock.return_value=5
        self.loader.side_effect=TimeoutError('private')
        stale=self.run_join()
        self.assertEqual(stale.display_state,'stale_snapshot')
        self.assertTrue(stale.predictions.winProbability.equals(first.predictions.winProbability))
