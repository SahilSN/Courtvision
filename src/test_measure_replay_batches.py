from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from measure_replay_batches import measure


class MeasureReplayBatchTest(unittest.TestCase):
    def test_observes_checkpoints_without_running_jobs(self):
        start = '2026-10-27T21:00:00+00:00'
        end = '2026-10-27T21:00:30+00:00'
        states = [
            {'workerPhase': 'processing', 'heartbeatAt': start,
             'batchGameIds': ['a', 'b'], 'batchSeason': '2025-26'},
            {'workerPhase': 'between_batches', 'heartbeatAt': end,
             'health': {'checkedAt': end}, 'games': {'a': {'status': 'prepared'}, 'b': {'status': 'blocked'}}},
        ]
        with tempfile.TemporaryDirectory() as directory, \
                patch('measure_replay_batches.read_json', side_effect=states), \
                patch('measure_replay_batches.time.sleep'), \
                patch('measure_replay_batches.time.monotonic', return_value=0):
            records = measure(Path(directory), 'normal', samples=1)
        self.assertEqual(records[0]['seconds'], 30)
        self.assertEqual(records[0]['prepared'], 1)
        self.assertEqual(records[0]['gamesPerMinute'], 2)


if __name__ == '__main__':
    unittest.main()
