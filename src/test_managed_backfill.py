import fcntl
import json
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch

from install_macos_backfill import build_launch_agent
from install_macos_updates import build_launch_agent as nightly_agent
from intelligence_health import backfill_health
from run_managed_backfill import main


class ManagedBackfillTest(unittest.TestCase):
    def test_login_and_failure_recovery_without_new_nightly_schedule(self):
        root = Path("/tmp/Courtvision Test")
        agent = plistlib.loads(plistlib.dumps(build_launch_agent(root)))
        self.assertTrue(agent["RunAtLoad"])
        self.assertEqual(agent["KeepAlive"], {"SuccessfulExit": False})
        self.assertEqual(agent["ThrottleInterval"], 300)
        self.assertNotIn("StartCalendarInterval", agent)
        self.assertNotIn("StartInterval", agent)
        self.assertTrue(all(Path(p).is_absolute() for p in agent["ProgramArguments"]))
        self.assertEqual(nightly_agent(root)["StartCalendarInterval"], {"Hour": 1, "Minute": 0})

    def health(self, directory, state, active=False):
        runtime = Path(directory) / "results/player_intelligence/.runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        (runtime / "status.json").write_text(json.dumps(state))
        with (runtime / "runner.lock").open("a") as lock:
            if active:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return backfill_health(directory)

    def test_stale_running_status_is_not_live_without_lock_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIn("not running", self.health(directory, {"status": "running"}))

    def test_source_retry_and_upload_retry_are_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIn("source retry", self.health(directory, {"status": "waiting"}, True))
            self.assertIn("upload pending", self.health(directory,
                {"status": "running", "publication": {"status": "retry_pending"}}, True))

    def test_missing_or_invalid_health_is_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIn("unavailable", backfill_health(directory))
            self.assertIn("unavailable", self.health(directory, []))

    def test_successful_completion_returns_zero_and_rotates_logs(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch("run_managed_backfill.ROOT_DIR", Path(directory)), \
             patch("run_managed_backfill.run_backfill", return_value=0) as runner:
            self.assertEqual(main(), 0)
            self.assertEqual(runner.call_args.kwargs["publish_every_games"], 500)
            self.assertTrue((Path(directory) / "results/player_intelligence/.runtime/backfill.log").exists())

    def test_unexpected_failure_returns_nonzero_for_launchd_restart(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch("run_managed_backfill.ROOT_DIR", Path(directory)), \
             patch("run_managed_backfill.run_backfill", side_effect=RuntimeError("test")):
            self.assertEqual(main(), 1)


if __name__ == "__main__":
    unittest.main()
