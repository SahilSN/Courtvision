import fcntl
import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

import pandas as pd

from install_macos_updates import build_launch_agent
from run_nightly_intelligence import git, nightly_due, publish_current_data, run_nightly


class NightlyJobTest(unittest.TestCase):
    def setUp(self):
        checker = patch('run_nightly_intelligence.refresh_coverage', return_value={'status': 'success'})
        checker.start()
        self.addCleanup(checker.stop)

    def test_coverage_failure_still_publishes_intelligence_but_marks_incomplete(self):
        with tempfile.TemporaryDirectory() as directory:
            publisher = Mock(return_value='published')
            code = run_nightly(directory,
                refresher=Mock(return_value={'pipelines': {'teams': {'status': 'success'}}}),
                publisher=publisher, coverage_checker=Mock(side_effect=ValueError('missing game')))
            status = json.loads((Path(directory) / 'results/.runtime/nightly/status.json').read_text())
            self.assertEqual(code, 1)
            self.assertEqual(status['recordCoverage']['status'], 'failed')
            publisher.assert_called_once()

    def test_calendar_is_once_nightly_with_absolute_venv_paths(self):
        agent = build_launch_agent(Path("/tmp/Courtvision Test"))
        self.assertEqual(agent["StartCalendarInterval"], {"Hour": 1, "Minute": 0})
        self.assertTrue(agent["RunAtLoad"])
        self.assertNotIn("StartInterval", agent)
        self.assertEqual(agent["ProgramArguments"][0], str(Path("/tmp/Courtvision Test").resolve() / ".venv/bin/python"))
        self.assertIn("--scheduled", agent["ProgramArguments"])

    def test_login_catchup_skips_completed_window_and_retries_failed_window(self):
        previous = {"status": "success", "finishedAt": "2026-10-23T01:05:00-07:00"}
        self.assertFalse(nightly_due(previous, datetime.fromisoformat("2026-10-23T09:00:00-07:00")))
        self.assertTrue(nightly_due(previous, datetime.fromisoformat("2026-10-24T01:00:00-07:00")))
        self.assertFalse(nightly_due(previous, datetime.fromisoformat("2026-10-24T00:30:00-07:00")))
        self.assertTrue(nightly_due({**previous, "status": "failed"}, datetime.fromisoformat("2026-10-23T09:00:00-07:00")))

    def test_incomplete_refresh_publishes_health_but_returns_failure(self):
        refresher = Mock(return_value={"pipelines": {"teams": {"status": "success"},
                                                   "players": {"status": "partial"}}})
        publisher = Mock(return_value="published-commit")
        with tempfile.TemporaryDirectory() as directory:
            result = run_nightly(directory, refresher=refresher, publisher=publisher)
            status = json.loads((Path(directory) / "results/.runtime/nightly/status.json").read_text())
        self.assertEqual(result, 1)
        self.assertEqual(status["status"], "incomplete")
        publisher.assert_called_once()

    def test_publication_failure_is_visible(self):
        refresher = Mock(return_value={"pipelines": {"players": {"status": "success"}}})
        publisher = Mock(side_effect=RuntimeError("GitHub unavailable"))
        with tempfile.TemporaryDirectory() as directory:
            result = run_nightly(directory, refresher=refresher, publisher=publisher)
            status = json.loads((Path(directory) / "results/.runtime/nightly/status.json").read_text())
        self.assertEqual(result, 1)
        self.assertEqual(status["status"], "failed")
        self.assertIn("GitHub unavailable", status["error"])

    def test_overlapping_run_does_not_call_updater(self):
        refresher = Mock()
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "results/.runtime/nightly"
            runtime.mkdir(parents=True)
            with (runtime / "update.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.assertEqual(run_nightly(directory, refresher=refresher), 0)
        refresher.assert_not_called()

    def test_isolated_publish_preserves_user_index_and_excludes_code(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            remote, source = base / "remote.git", base / "source"
            source.mkdir()
            git(base, "init", "--bare", "--initial-branch=main", str(remote))
            git(source, "init", "--initial-branch=main")
            git(source, "config", "user.name", "Test")
            git(source, "config", "user.email", "test@example.com")
            (source / ".gitignore").write_text("results/.runtime/\n")
            (source / "README.md").write_text("original code\n")
            games = source / "results/player_intelligence/2026-27_player_game_v1.csv"
            games.parent.mkdir(parents=True)
            pd.DataFrame({"gameId": ["0022600001"]}).to_csv(games, index=False)
            git(source, "add", ".")
            git(source, "commit", "-m", "initial")
            git(source, "remote", "add", "origin", str(remote))
            git(source, "push", "-u", "origin", "main")
            (source / "README.md").write_text("user-staged code\n")
            git(source, "add", "README.md")
            original_index = git(source, "diff", "--cached", "--binary").stdout
            original_head = git(source, "rev-parse", "HEAD").stdout
            pd.DataFrame({"gameId": ["0022600001", "0022600002"]}).to_csv(games, index=False)
            publish_current_data(source)
            self.assertEqual(git(source, "diff", "--cached", "--binary").stdout, original_index)
            self.assertEqual(git(source, "rev-parse", "HEAD").stdout, original_head)
            published_readme = git(base, "--git-dir", str(remote), "show", "main:README.md").stdout
            self.assertEqual(published_readme, "original code\n")
            published_games = git(base, "--git-dir", str(remote), "show", "main:" + str(games.relative_to(source))).stdout
            self.assertIn("0022600002", published_games)
            pd.DataFrame({"gameId": ["0022600001"]}).to_csv(games, index=False)
            with self.assertRaisesRegex(ValueError, "fewer games"):
                publish_current_data(source)


if __name__ == "__main__":
    unittest.main()
