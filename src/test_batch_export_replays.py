import fcntl
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from batch_export_replays import run_batch
from live_artifacts import write_json
from replay_catalog import INDEX


class BatchExportTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        write_json(self.root/INDEX,{'schemaVersion':1,'games':[]})

    def cache(self,gid='0022500002',impact=True):
        for path in [f'data/cache/analysis/v1_v7/2025-26_{gid}_top3.pkl',
                     f'data/cache/box_score/v1/{gid}.pkl',
                     *([f'results/player_wpa_v3_{gid}_summary.csv'] if impact else [])]:
            target=self.root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b'trusted test fixture')

    def test_limit_checkpoints_and_missing_inputs_are_not_scheduled(self):
        self.cache();self.cache('0022500003');self.cache('0022500004',impact=False)
        with patch('batch_export_replays.prepare',return_value={'games':[]}) as export:
            report=run_batch(self.root,self.root,limit=1)
        self.assertEqual(export.call_count,1)
        self.assertEqual((report['exported'],report['blocked'],report['pending']),(1,1,1))
        self.assertTrue((self.root/'results/.runtime/replay-export/status.json').exists())

    def test_failures_resume_without_repeating_unchanged_bad_cache(self):
        self.cache()
        with patch('batch_export_replays.prepare',side_effect=ValueError('private source error')) as export:
            self.assertEqual(run_batch(self.root,self.root)['blocked'],1)
            run_batch(self.root,self.root)
            self.assertEqual(export.call_count,1)
            run_batch(self.root,self.root,retry_blocked=True)
            self.assertEqual(export.call_count,2)
        with patch('batch_export_replays.prepare',return_value={'games':[]}) as export:
            (self.root/'data/cache/analysis/v1_v7/2025-26_0022500002_top3.pkl').write_bytes(b'changed source')
            self.assertEqual(run_batch(self.root,self.root)['exported'],1)
            export.assert_called_once()

    def test_budget_exhaustion_never_calls_export(self):
        self.cache()
        with patch('batch_export_replays.prepare') as export:
            result=run_batch(self.root,self.root,clock=iter([0,61]).__next__)
            self.assertEqual(result['pending'],1);export.assert_not_called()

    def test_lock_prevents_concurrent_batches(self):
        runtime=self.root/'results/.runtime/replay-export';runtime.mkdir(parents=True)
        with (runtime/'batch.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):run_batch(self.root,self.root)


if __name__=='__main__':unittest.main()
