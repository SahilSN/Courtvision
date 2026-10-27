from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from deployment_health import intelligence_status, nightly_status
from live_artifacts import write_json
from live_diagnostics import RefreshDiagnostics
from run_nightly_intelligence import nightly_due, run_nightly
from update_intelligence import load_update_status
from streamlit.testing.v1 import AppTest
from unittest.mock import patch


class DeploymentHealthTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.now = datetime(2026,10,27,5,tzinfo=timezone.utc)
        self.path = self.root/'results/season_intelligence/2026-27_update_status_v1.json'
        self.item = dict(status='success',checkedAt=self.now.isoformat(),processedGames=43,
                         completedGames=43,gamesThrough='2026-10-25',error=None)

    def save(self, **overrides):
        write_json(self.path,dict(season='2026-27',pipelines=dict(teams={**self.item,**overrides},players=self.item)))

    def report(self):
        return intelligence_status(self.root,self.now)['pipelines']

    def test_current_success_is_sanitized_and_independent(self):
        self.save(status='partial',processedGames=42,error='PRIVATE RAW ERROR')
        report = self.report()
        self.assertEqual(report['teams']['state'],'partial')
        self.assertEqual(report['players']['state'],'success')
        self.assertNotIn('PRIVATE',json.dumps(report))

    def test_old_success_is_stale_and_future_or_naive_is_unavailable(self):
        self.save(checkedAt=(self.now-timedelta(hours=37)).isoformat())
        self.assertEqual(self.report()['teams']['state'],'stale')
        for checked in ((self.now+timedelta(seconds=1)).isoformat(),'2026-10-27T05:00:00'):
            self.save(checkedAt=checked)
            self.assertEqual(self.report()['teams']['state'],'unavailable')

    def test_invalid_counts_and_contradictory_success_fail_closed(self):
        for updates in (dict(processedGames=True),dict(completedGames=42),dict(completedGames=None),
                        dict(pendingGameIds=['0022600001']),dict(failures=['private']),
                        dict(gamesThrough='2026-10-29'),dict(status='invented'),dict(error='private')):
            self.save(**updates)
            self.assertEqual(self.report()['teams']['state'],'unavailable')

    def test_bad_missing_or_wrong_season_artifact_is_unavailable(self):
        self.assertEqual(self.report()['teams']['state'],'unavailable')
        self.path.parent.mkdir(parents=True)
        for raw in ('{','[]','{"season":"2025-26"}', '{"season":"2026-27","pipelines":[]}'):
            self.path.write_text(raw)
            self.assertEqual(self.report()['teams']['state'],'unavailable')
            self.assertEqual(load_update_status(self.path),{} if raw!='{"season":"2025-26"}' else {'season':'2025-26'})

    def test_saved_local_attempt_never_infers_worker_liveness(self):
        path=self.root/'results/.runtime/nightly/status.json'
        write_json(path,dict(status='failed',startedAt=self.now.isoformat(),finishedAt=self.now.isoformat(),
                             error='SECRET ERROR',publication=None))
        report=nightly_status(self.root)
        self.assertEqual(report['state'],'failed')
        self.assertEqual(report['publication'],'not-recorded')
        self.assertNotIn('SECRET',json.dumps(report))
        self.assertIn('not-worker-liveness',report['scope'])

    def test_corrupt_or_future_saved_nightly_status_does_not_suppress_catchup(self):
        for saved in ({},[],{'status':'success','finishedAt':'bad'},
                      {'status':'success','finishedAt':'2026-10-29T05:00:00+00:00'},
                      {'status':'success','finishedAt':'2026-10-27T05:00:00'}):
            self.assertTrue(nightly_due(saved,self.now))
        path=self.root/'results/.runtime/nightly/status.json'
        path.parent.mkdir(parents=True)
        path.write_text('{broken')
        runner=Mock(return_value={'pipelines':dict(teams={'status':'success'},players={'status':'success'})})
        self.assertEqual(run_nightly(self.root,scheduled=True,refresher=runner,publisher=Mock(return_value='published'),
                                    coverage_checker=Mock(return_value={'status':'success'})),0)
        runner.assert_called_once()

    def test_missing_pipeline_cannot_be_reported_as_success(self):
        code=run_nightly(self.root,refresher=Mock(return_value={'pipelines':{}}),
                         publisher=Mock(return_value='published'),coverage_checker=Mock(return_value={'status':'success'}))
        self.assertEqual(code,1)

    def test_feed_observations_are_bounded_fresh_and_updated_even_when_logs_throttle(self):
        clock=Mock(return_value=0)
        log=RefreshDiagnostics(clock=clock,emit=Mock(),max_entries=2)
        log.record('0022600127','unavailable',.1,error_type='PRIVATE RAW ERROR')
        clock.return_value=10
        self.assertFalse(log.record('0022600127','unavailable',.1))
        self.assertEqual(log.recent()[0]['observedSecondsAgo'],0)
        self.assertNotIn('PRIVATE',json.dumps(log.recent()))
        log.record('0022600126','scheduled',.1)
        log.record('0022600125','validated_snapshot',.1)
        self.assertEqual(len(log.recent()),2)
        clock.return_value=131
        self.assertEqual(log.recent(),[])

    def test_health_ui_is_read_only_and_no_raw_errors_escape(self):
        self.save(status='failed',error='PRIVATE RAW ERROR')
        script=f'from deployment_health_view import render_health\nrender_health({str(self.root)!r})'
        with patch('requests.sessions.Session.request',side_effect=AssertionError('No HTTP allowed')), \
             patch('subprocess.run',side_effect=AssertionError('No worker allowed')):
            app=AppTest.from_string(script,default_timeout=20).run()
        self.assertFalse(app.exception)
        text=' '.join(str(element.value) for element in [*app.caption,*app.markdown])
        self.assertIn('Teams · failed',text)
        self.assertIn('Players · success',text)
        self.assertIn('cannot prove the Mac is awake',text)
        self.assertNotIn('PRIVATE RAW ERROR',text)
        self.assertFalse(app.button)


if __name__=='__main__':
    unittest.main()
