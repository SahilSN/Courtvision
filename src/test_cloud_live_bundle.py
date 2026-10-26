from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import json
import unittest
from unittest.mock import Mock, patch

from cloud_live_bundle import get_live_bundle
from live_snapshot_cache import LiveSnapshotCache, SnapshotUnavailable
from feed_progress import FeedProgress
from cloud_espn_adapter import normalize_snapshot


class BundleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = Path(__file__).parent/'fixtures'
        cls.feed = json.loads((directory/'espn_contract_0022500001.json').read_text())
        cls.feed['summary']['boxscore']['players'] = json.loads((directory/'espn_box_0022500001.json').read_text())['players']

    def setUp(self):
        self.clock = Mock(return_value=0)
        self.cache = LiveSnapshotCache(ttl=5,max_age=20,retry_delay=5,clock=self.clock)
        blocker = patch('requests.sessions.Session.request',side_effect=AssertionError('Unexpected network'))
        blocker.start();self.addCleanup(blocker.stop)

    def get(self, loader):
        return get_live_bundle(self.cache,self.feed['canonical'],loader)

    def test_concurrent_panels_one_fetch_and_defensive_results(self):
        loader = Mock(return_value=self.feed)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.get(loader),range(4)))
        loader.assert_called_once()
        self.assertEqual(int(results[0].timeline.scoreHome.iloc[-1]),125)
        self.assertEqual(sorted(results[0].box['teams'].points),[124,125])
        results[0].box['teams'].loc[:,'points'] = 999
        self.assertEqual(sorted(self.get(loader).box['teams'].points),[124,125])

    def test_unreconciled_refresh_retains_both_old_panels_and_recovers(self):
        self.get(lambda:self.feed)
        broken = deepcopy(self.feed)
        broken['summary']['boxscore']['players'][0]['statistics'][0]['totals'][1]='999'
        self.clock.return_value=5
        stale=self.get(lambda:broken)
        self.assertTrue(stale.is_stale)
        self.assertEqual(stale.refresh_error_type,'ProviderContextUnavailable')
        self.assertEqual(sorted(stale.box['teams'].points),[124,125])
        self.clock.return_value=10
        fresh=self.get(lambda:self.feed)
        self.assertFalse(fresh.is_stale)
        self.assertIsNone(fresh.refresh_error_type)

    def test_partial_cold_feed_unavailable_not_half_a_panel(self):
        broken=deepcopy(self.feed)
        broken['summary']['plays']=broken['summary']['plays'][:100]
        with self.assertRaises(SnapshotUnavailable): self.get(lambda:broken)

    def test_expired_pair_not_served_after_failure(self):
        self.get(lambda:self.feed)
        self.clock.return_value=21
        with self.assertRaises(SnapshotUnavailable): self.get(Mock(side_effect=TimeoutError('private detail')))

    def test_changed_canonical_team_not_hidden_by_warm_cache(self):
        self.get(lambda:self.feed)
        wrong={**self.feed['canonical'],'homeTeamId':1610612747}
        with self.assertRaises(ValueError): get_live_bundle(self.cache,wrong,lambda:self.feed)

    def test_duplicate_correction_refused_and_last_valid_kept(self):
        self.get(lambda:self.feed)
        broken=deepcopy(self.feed)
        broken['summary']['plays'].append(deepcopy(broken['summary']['plays'][0]))
        self.clock.return_value=5
        self.assertTrue(self.get(lambda:broken).is_stale)

    def test_single_timeline_per_joint_pass_and_progress_across_fresh_fetches(self):
        feed=deepcopy(self.feed)
        feed['summary']['header']['competitions'][0]['status']['type'].update(
            state='in',name='STATUS_IN_PROGRESS',completed=False)
        tracker=FeedProgress(threshold=10,clock=self.clock)
        with patch('cloud_live_bundle.normalize_snapshot',wraps=normalize_snapshot) as normalize:
            first=get_live_bundle(self.cache,feed['canonical'],lambda:feed,tracker)
            self.assertEqual(normalize.call_count,2)  # before installation + caller copy
            self.assertEqual(first.progress_state,'observing')
            self.clock.return_value=11
            fresh=get_live_bundle(self.cache,feed['canonical'],lambda:feed,tracker)
            self.assertFalse(fresh.is_stale)
            self.assertEqual(fresh.progress_state,'possibly_stalled')
            self.assertEqual(fresh.unchanged_seconds,11)
            self.assertEqual(normalize.call_count,4)
