from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from live_artifacts import read_json, write_json
from run_live_preflight import invariant, run, paths, semantic
from official_live_rosters import roster_candidates
from live_snapshot_cache import LiveSnapshotCache, SnapshotKey, SnapshotUnavailable, unavailable_reason
from cloud_espn_adapter import PlayerIdentityUnavailable
from test_daily_live_preparation import DailyPreparationTest


class PreflightTest(unittest.TestCase):
    def setUp(self):
        self.fixture=DailyPreparationTest(methodName='test_prepare_is_bounded_and_automatic_policy_has_no_network')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.prepare()

    def test_refresh_preserves_context_and_original_expiry_and_skips_timestamp_only_push(self):
        f=self.fixture
        context=f.context_path.read_bytes()
        original=read_json(f.root/paths()[2])
        def preparer(stage,now):
            from prepare_daily_live import prepare_daily_live
            return prepare_daily_live(stage,now=now,fetcher=f.fetcher)
        def publisher(root,stage,context,old):
            invariant(old,read_json(stage/paths()[2]),context)
            return 'test-commit'
        now=f.now+timedelta(hours=10)
        with patch('run_live_preflight.active_games',return_value=tuple(original['gameIds'])), \
                patch('run_live_preflight.publish_preflight',side_effect=publisher):
            # Inject explicitly; default bound functions are intentionally immutable.
            from unittest.mock import Mock
            publish=Mock(side_effect=publisher)
            first=run(f.root,now=now,preparer=preparer,publisher=publish)
            second=run(f.root,now=now+timedelta(minutes=16),preparer=preparer,publisher=publish)
        self.assertEqual(first['status'],'published')
        self.assertEqual(second['status'],'unchanged')
        self.assertEqual(publish.call_count,1)
        self.assertEqual(f.context_path.read_bytes(),context)
        current=read_json(f.root/paths()[2])
        self.assertEqual(current['issuedAt'],original['issuedAt'])
        self.assertEqual(current['expiresAt'],original['expiresAt'])

    def test_expired_policy_does_no_preparation(self):
        from unittest.mock import Mock
        f=self.fixture
        prepare,publish=Mock(),Mock()
        with patch('run_live_preflight.active_games',return_value=()):
            self.assertEqual(run(f.root,now=f.now,preparer=prepare,publisher=publish)['status'],'inactive_or_expired')
        prepare.assert_not_called(); publish.assert_not_called()

    def test_invariant_rejects_expiry_or_game_changes(self):
        f=self.fixture
        old=read_json(f.root/paths()[2])
        for key,value in [('expiresAt',(f.now+timedelta(hours=23)).isoformat()),('gameIds',old['gameIds'][:1])]:
            changed=deepcopy(old); changed[key]=value
            with self.assertRaises(ValueError):invariant(old,changed,f.context)

    def test_reason_is_safe_and_preserved_during_cache_backoff(self):
        cache=LiveSnapshotCache()
        key=SnapshotKey('espn','0022600001','2026-27','Regular Season','2026-10-27')
        def bad():raise PlayerIdentityUnavailable('private raw details must not be shown')
        for _ in range(2):
            with self.assertRaises(SnapshotUnavailable) as captured:cache.get(key,bad)
            self.assertEqual(captured.exception.error_type,'PlayerIdentityUnavailable')
            message=unavailable_reason(captured.exception)
            self.assertIn('exact NBA player identity',message)
            self.assertNotIn('private raw',message)

    def test_unreadable_provider_response_is_not_blame_on_context(self):
        import ast
        source=Path(__file__).with_name('live_beta_view.py').read_text()
        node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='display_unavailable_reason')
        namespace={'unavailable_reason':unavailable_reason}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<display-reason>','exec'),namespace)
        message=namespace['display_unavailable_reason'](SnapshotUnavailable('raw', 'JSONDecodeError'))
        self.assertIn('unreadable response',message)
        self.assertNotIn('raw',message)

    def test_transient_roster_timeout_retains_original_evidence_timestamp(self):
        from prepare_daily_live import prepare_daily_live
        f=self.fixture
        old=read_json(f.root/paths()[0])
        def timed_out(url):
            if 'commonteamroster?' in url:raise TimeoutError()
            return f.fetch(url)
        prepare_daily_live(f.root,now=f.now+timedelta(hours=1),fetcher=timed_out)
        current=read_json(f.root/paths()[0])
        self.assertTrue(all(t['status']=='verified' for t in current['teams']))
        self.assertEqual(current['teams'][0]['checkedAt'],old['teams'][0]['checkedAt'])
        self.assertEqual(current['teams'][0]['lastFetchErrorType'],'TimeoutError')
        team=current['teams'][0]; player=team['players'][0]
        self.assertEqual(roster_candidates(player['fullName'],'2026-27',team['teamId'],f.day,
            path=f.root/paths()[0],now=f.now+timedelta(hours=2)),{player['personId']})
        # A new artifact timestamp must not revive expired per-team evidence.
        for item in current['teams']:item['checkedAt']=(f.now-timedelta(hours=37)).isoformat()
        write_json(f.root/paths()[0],current)
        self.assertFalse(roster_candidates(player['fullName'],'2026-27',team['teamId'],f.day,
            path=f.root/paths()[0],now=f.now+timedelta(hours=2)))

    def test_empty_pregame_summary_does_not_claim_roster_inspected(self):
        from prepare_daily_live import prepare_daily_live
        f=self.fixture
        def empty_summary(url):
            data,meta=f.fetch(url)
            if 'summary?' in url:data['boxscore']['players']=[]
            return data,meta
        prepare_daily_live(f.root,now=f.now,fetcher=empty_summary)
        manifest=read_json(f.root/paths()[2])
        self.assertTrue(all(g['status']=='unavailable' for g in manifest['summaryInspections']))


if __name__=='__main__':unittest.main()
