import fcntl
from pathlib import Path
import tempfile
import pickle
import unittest
from unittest.mock import patch

from rebuild_saved_replays import rebuild


class RebuildReplayTest(unittest.TestCase):
    def test_remote_fallback_is_blocked_and_source_cache_unchanged(self):
        import live_analysis
        from live_artifacts import write_json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json(root / 'results/replay_catalog/index_v1.json', {'schemaVersion': 1, 'games': []})
            cache = root / 'data/cache/analysis/v1_v7/2025-26_0022500001_top3.pkl'
            cache.parent.mkdir(parents=True)
            cache.write_bytes(pickle.dumps({'cache_version': 'v1_v7', 'result': {
                'game_id': '0022500001', 'is_final': True, 'game_date': '2025-10-21'}}))
            original = cache.read_bytes()
            box = root / 'data/cache/box_score/v1/0022500001.pkl'
            box.parent.mkdir(parents=True)
            box.write_bytes(b'unchanged box')
            def remote_attempt(*args, **kwargs):
                return live_analysis.fetch_live_play_by_play('0022500001')
            with patch.object(live_analysis, 'analyze_live_game', side_effect=remote_attempt), \
                    patch('rebuild_saved_replays.prepare') as export:
                report = rebuild(root, root, '2025-26', ['0022500001'])
            self.assertEqual(report['games']['0022500001']['status'], 'blocked')
            self.assertIn('cannot acquire', report['games']['0022500001']['reason'])
            self.assertEqual(cache.read_bytes(), original)
            self.assertEqual(box.read_bytes(), b'unchanged box')
            export.assert_not_called()

    def test_bounds_duplicates_and_identity_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for ids in ([], ['0022500001'] * 2, ['0022500001'] * 6, ['0022400001']):
                with self.assertRaises(ValueError):
                    rebuild(directory, directory, '2025-26', ids)

    def test_unlisted_game_cannot_be_generated(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('rebuild_saved_replays.season_catalog', return_value=([], False)):
                with self.assertRaises(ValueError):
                    rebuild(directory, directory, '2025-26', ['0022500001'], True)

    def test_rebuild_shares_exporter_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / 'results/.runtime/replay-export'
            runtime.mkdir(parents=True)
            with (runtime / 'batch.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaises(BlockingIOError):
                    rebuild(directory, directory, '2025-26', ['0022500001'])


if __name__ == '__main__':
    unittest.main()
