from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from live_artifacts import write_json
from replay_progress import progress, page, start_progress_server


class ReplayProgressTest(unittest.TestCase):
    def test_local_pending_and_published_counts_are_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json(root / 'results/.runtime/replay-expansion/state.json', {
                'games': {'a': {'status': 'blocked'}}, 'dailyAttempts': 250,
                'publishedReplayCount': 58, 'workerPhase': 'processing',
                'batchGameIds': ['0022500001'], 'batchSeason': '2025-26'})
            with patch('replay_progress.read_index', return_value={
                    str(i): {'season': '2025-26'} for i in range(63)}):
                value = progress(root)
            self.assertEqual((value['prepared'], value['published'], value['awaitingPublication']), (63, 58, 5))
            self.assertEqual(value['attemptsToday'], 250)
            self.assertEqual(value['blocked'], 1)
            value['batchSeason'] = '<script>bad</script>'
            rendered = page(value)
            self.assertNotIn('<script>', rendered)
            self.assertIn('no daily cap', rendered)

    def test_listener_is_loopback_only(self):
        with patch('replay_progress.ThreadingHTTPServer') as server, \
                patch('replay_progress.threading.Thread'):
            start_progress_server('/tmp/test', port=8520)
            self.assertEqual(server.call_args.args[0], ('127.0.0.1', 8520))


if __name__ == '__main__':
    unittest.main()
