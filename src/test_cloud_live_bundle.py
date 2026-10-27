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
    def test_concurrent_score_retries_share_one_acquisition(self):
        loader=Mock(side_effect=[self.lagging(),self.feed])
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:self.get(loader),range(4)))
        self.assertEqual(loader.call_count,2)
        self.assertTrue(all(not r.is_stale for r in results))
        self.assertTrue(all(r.timeline.equals(results[0].timeline) for r in results))

    def lagging(self):
        broken=deepcopy(self.feed)
        broken['summary']['header']['competitions'][0]['competitors'][0]['score']=str(
            int(broken['summary']['header']['competitions'][0]['competitors'][0]['score'])+2)
        return broken

    def test_score_retry_recovers_whole_pair_without_mutating_previous(self):
        first=self.get(lambda:self.feed)
        self.clock.return_value=5
        loader=Mock(side_effect=[self.lagging(),self.feed])
        with patch('cloud_live_bundle.time.sleep') as pause:
            result=self.get(loader)
        self.assertEqual(loader.call_count,2);pause.assert_called_once_with(.5)
        self.assertFalse(result.is_stale)
        self.assertTrue(first.timeline.equals(result.timeline))
        self.assertTrue(first.box['players'].equals(result.box['players']))

    def test_exhausted_score_retry_keeps_pair_and_expiry_still_blocks(self):
        self.get(lambda:self.feed);self.clock.return_value=5
        loader=Mock(return_value=self.lagging())
        with patch('cloud_live_bundle.time.sleep'):
            result=self.get(loader)
        self.assertTrue(result.is_stale);self.assertEqual(loader.call_count,2)
        self.assertEqual(result.refresh_error_type,'ScoreSectionsUnreconciled')
        self.clock.return_value=21
        with patch('cloud_live_bundle.time.sleep'),self.assertRaises(SnapshotUnavailable):self.get(loader)
        self.assertEqual(loader.call_count,4)

    def test_identity_and_transport_failure_never_retried(self):
        broken=deepcopy(self.feed)
        broken['summary']['boxscore']['players'][0]['statistics'][0]['athletes'][0]['athlete']['displayName']='Unresolved Player'
        for loader in (Mock(return_value=broken),Mock(side_effect=TimeoutError('private'))):
            self.cache=LiveSnapshotCache(ttl=5,max_age=20,retry_delay=5,clock=self.clock)
            with patch('cloud_live_bundle.time.sleep') as pause,self.assertRaises(SnapshotUnavailable):self.get(loader)
            self.assertEqual(loader.call_count,1);pause.assert_not_called()

    def test_retry_budget_stops_before_second_request(self):
        loader=Mock(return_value=self.lagging())
        with patch('cloud_live_bundle.time.monotonic',side_effect=[0,8]),patch('cloud_live_bundle.time.sleep') as pause:
            with self.assertRaises(SnapshotUnavailable):self.get(loader)
        self.assertEqual(loader.call_count,1);pause.assert_not_called()

    def test_coherent_stat_correction_replaces_pair_without_mutating_previous_result(self):
        first=self.get(lambda:self.feed)
        corrected=deepcopy(self.feed)
        stats=corrected['summary']['boxscore']['players'][0]['statistics'][0]
        index=stats['labels'].index('AST')
        previous=int(stats['athletes'][0]['stats'][index])
        stats['athletes'][0]['stats'][index]=str(previous+1)
        stats['totals'][index]=str(int(stats['totals'][index])+1)
        self.clock.return_value=5
        refreshed=self.get(lambda:corrected)
        self.assertFalse(refreshed.is_stale)
        self.assertEqual(int(refreshed.box['players'].assists.iloc[0]),previous+1)
        self.assertEqual(int(first.box['players'].assists.iloc[0]),previous)

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
        self.assertEqual(stale.refresh_error_type,'ScoreSectionsUnreconciled')
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
