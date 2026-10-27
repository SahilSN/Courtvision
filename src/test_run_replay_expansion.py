from datetime import datetime, timezone
import fcntl
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from live_artifacts import read_json, write_json
from run_replay_expansion import choose_batch, publication_due, run, publish, continuous


class ReplayExpansionTest(unittest.TestCase):
    def test_nightly_due_and_backoff(self):
        now = datetime(2026, 10, 28, 9, tzinfo=timezone.utc)  # 2 a.m. Pacific
        self.assertTrue(publication_due({}, now))
        self.assertFalse(publication_due({'publishedDay': '2026-10-28'}, now))
        self.assertFalse(publication_due({'nextPublishRetry': now.timestamp() + 1}, now))
        self.assertFalse(publication_due({}, now.replace(hour=7)))

    def test_worker_lock_prevents_overlap(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / 'results/.runtime/replay-expansion'
            runtime.mkdir(parents=True)
            with (runtime / 'worker.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaises(BlockingIOError):
                    run(directory)

    def test_unchanged_blocked_inputs_skipped_changed_inputs_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ['data/training/2025-26_training_v4_base.csv', 'data/processed/0022500001.csv',
                         'data/cache/box_score/v1/0022500001.pkl',
                         'results/player_wpa_v3_0022500001_summary.csv',
                         'models/win_probability_mlp_v7.pt', 'models/win_probability_scaler_v7.pkl']:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'test')
            with patch('run_replay_expansion.read_index', return_value={}), \
                    patch('run_replay_expansion.catalog_seasons', return_value=['2024-25', '2025-26']), \
                    patch('run_replay_expansion.season_catalog', return_value=([{'gameId': '0022500001'}], False)):
                season, batch = choose_batch(root, root, {'games': {}})
                self.assertEqual(season, '2025-26')
                state = {'games': {'0022500001': {'status': 'blocked', 'fingerprint': batch[0][1]}}}
                self.assertEqual(choose_batch(root, root, state), (None, []))
                (root / 'data/processed/0022500001.csv').write_bytes(b'updated')
                self.assertEqual(len(choose_batch(root, root, state)[1]), 1)

    def test_no_daily_cap_and_publication_failure_backoff(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / 'results/.runtime/replay-expansion/state.json'
            write_json(state_path, {'games': {}, 'attemptDay': '2026-10-28', 'dailyAttempts': 200})
            now = datetime(2026, 10, 28, 9, tzinfo=timezone.utc)
            with patch('run_replay_expansion.seed_workspace'), \
                    patch('run_replay_expansion.read_index', return_value={}), \
                    patch('run_replay_expansion.choose_batch', return_value=(None, [])) as choose, \
                    patch('run_replay_expansion.publish', side_effect=RuntimeError('offline')):
                result = run(root, now=now)
                choose.assert_called_once()
                self.assertEqual(choose.call_args.args[-1], 5)
            self.assertEqual(result['publicationState'], 'retry_pending')
            saved = read_json(state_path)
            self.assertEqual(saved['nextPublishRetry'], now.timestamp() + 3600)
            self.assertNotIn('publishedDay', saved)

    def test_continuous_catchup_no_half_hour_wait_and_idle_backoff(self):
        with patch('run_replay_expansion.run', side_effect=[
                {'attempted': 5}, {'attempted': 5}, {'attempted': 0}]) as worker, \
                patch('run_replay_expansion.time.monotonic', return_value=1):
            sleeper = unittest.mock.Mock(side_effect=[None, None, KeyboardInterrupt])
            with self.assertRaises(KeyboardInterrupt):
                continuous('/tmp/worker-test', sleeper=sleeper)
            self.assertEqual([call.args[0] for call in sleeper.call_args_list], [2, 2, 60])
            self.assertEqual([call.kwargs['refresh'] for call in worker.call_args_list], [True, False, False])

    def test_corrupt_state_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'results/.runtime/replay-expansion/state.json'
            path.parent.mkdir(parents=True)
            path.write_text('broken')
            with self.assertRaises(ValueError):
                run(directory)

    def test_publisher_refuses_changed_remote_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / 'prepared'
            workspace.mkdir()
            fake = type('Result', (), {'stdout': 'https://example.invalid/repo', 'returncode': 0})()
            with patch('run_replay_expansion.git', return_value=fake) as git, \
                    patch('run_replay_expansion.read_index', side_effect=[
                        {'0022500001': {'sha256': 'old'}}, {'0022500001': {'sha256': 'new'}}]), \
                    patch('run_replay_expansion.load_catalog_replay'):
                with self.assertRaises(ValueError):
                    publish(root, workspace, {})
                self.assertFalse(any('push' in call.args for call in git.call_args_list))


if __name__ == '__main__':
    unittest.main()
