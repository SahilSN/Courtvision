import fcntl
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from run_historical_backfill import run_backfill


class BackfillRunnerTest(unittest.TestCase):
    def test_snapshot_lock_contention_is_retried(self):
        before = {"2025-26": {"processedGames": 0, "expectedGames": 1}}
        after = {"2025-26": {"processedGames": 1, "expectedGames": 1}}
        sleep = Mock()
        with tempfile.TemporaryDirectory() as directory, \
             patch("run_historical_backfill.progress", side_effect=[before, before, after]), \
             patch("run_historical_backfill.backfill_season", side_effect=[BlockingIOError(), []]):
            self.assertEqual(run_backfill(["2025-26"], directory, max_rounds=2, sleeper=sleep), 0)
        sleep.assert_called_once_with(2)

    def test_outage_backoff_is_bounded_and_health_remains_incomplete(self):
        coverage = {"2025-26": {"processedGames": 0, "expectedGames": 10}}
        errors = [{"gameId": "0022500001", "error": "timeout"}]
        sleep = Mock()
        with tempfile.TemporaryDirectory() as directory, \
             patch("run_historical_backfill.progress", return_value=coverage), \
             patch("run_historical_backfill.backfill_season", return_value=errors):
            code = run_backfill(["2025-26"], directory, cooldown=60,
                                max_cooldown=120, max_rounds=4, sleeper=sleep)
            state = json.loads((Path(directory) / ".runtime/status.json").read_text())
        self.assertEqual(code, 1)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [60, 120, 120])
        self.assertEqual(state["status"], "incomplete")
        self.assertEqual(state["failureCount"], 4)
        self.assertIsNone(state["lastProgressAt"])
        self.assertIsNone(state["nextRetryAt"])

    def test_success_records_progress_and_completes_without_waiting(self):
        before = {"2025-26": {"processedGames": 0, "expectedGames": 1}}
        after = {"2025-26": {"processedGames": 1, "expectedGames": 1}}
        sleep = Mock()
        with tempfile.TemporaryDirectory() as directory, \
             patch("run_historical_backfill.progress", side_effect=[before, after]), \
             patch("run_historical_backfill.backfill_season", return_value=[]):
            self.assertEqual(run_backfill(["2025-26"], directory, max_rounds=1, sleeper=sleep), 0)
            state = json.loads((Path(directory) / ".runtime/status.json").read_text())
        self.assertEqual(state["status"], "complete")
        self.assertIsNotNone(state["lastProgressAt"])
        sleep.assert_not_called()

    def test_wait_interruption_is_visible_and_preserves_coverage(self):
        coverage = {"2025-26": {"processedGames": 1, "expectedGames": 2}}
        with tempfile.TemporaryDirectory() as directory, \
             patch("run_historical_backfill.progress", return_value=coverage), \
             patch("run_historical_backfill.backfill_season", return_value=[]):
            code = run_backfill(["2025-26"], directory, sleeper=Mock(side_effect=KeyboardInterrupt))
            state = json.loads((Path(directory) / ".runtime/status.json").read_text())
        self.assertEqual(code, 130)
        self.assertEqual(state["status"], "interrupted")
        self.assertEqual(state["coverage"], coverage)

    def test_second_runner_skips_without_processing(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / ".runtime"
            runtime.mkdir()
            with (runtime / "runner.lock").open("a") as lock, \
                 patch("run_historical_backfill.progress") as read:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.assertEqual(run_backfill(["2025-26"], directory), 0)
                read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
