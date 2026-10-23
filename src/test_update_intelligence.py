import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import pandas as pd

from test_update_player_intelligence import completed_games
from update_intelligence import load_update_status, refresh_intelligence


class RefreshHealthTest(unittest.TestCase):
    def setUp(self):
        self.games = completed_games()
        self.discovery = Mock(return_value=self.games)
        self.teams = Mock(return_value={"history": self.games})
        self.players = Mock(return_value={"dataset": self.games, "failures": []})

    def refresh(self, directory, **kwargs):
        return refresh_intelligence(
            root=directory, discovery=self.discovery,
            team_runner=self.teams, player_runner=self.players, **kwargs,
        )

    def test_success_records_actual_coverage_and_shared_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            status = self.refresh(directory)
            path = Path(directory) / "results/season_intelligence/2026-27_update_status_v1.json"
            self.assertEqual(load_update_status(path), status)
        self.discovery.assert_called_once()
        self.assertIs(self.teams.call_args.kwargs["completed_games"], self.games)
        self.assertIs(self.players.call_args.kwargs["completed_games"], self.games)
        for pipeline in status["pipelines"].values():
            self.assertEqual(pipeline["status"], "success")
            self.assertEqual(pipeline["processedGames"], 2)
            self.assertEqual(pipeline["gamesThrough"], "2026-10-21")
            self.assertEqual(pipeline["pendingGameIds"], [])

    def test_team_failure_does_not_block_player_update(self):
        self.teams.side_effect = RuntimeError("temporary team failure")
        with tempfile.TemporaryDirectory() as directory:
            status = self.refresh(directory)
        self.players.assert_called_once()
        self.assertEqual(status["pipelines"]["teams"]["status"], "failed")
        self.assertEqual(status["pipelines"]["players"]["status"], "success")

    def test_partial_player_refresh_is_reported_and_retried(self):
        self.players.return_value = {"dataset": self.games.head(1), "failures": [
            {"gameId": "0022600002", "error": "source unavailable"}
        ]}
        with tempfile.TemporaryDirectory() as directory:
            status = self.refresh(directory)
            self.assertEqual(status["pipelines"]["players"]["status"], "partial")
            self.assertEqual(status["pipelines"]["players"]["pendingGameIds"], ["0022600002"])
            self.players.return_value = {"dataset": self.games, "failures": []}
            recovered = self.refresh(directory)
        self.assertEqual(recovered["pipelines"]["players"]["status"], "success")

    def test_discovery_failure_preserves_success_time_and_published_files(self):
        with tempfile.TemporaryDirectory() as directory:
            original = self.refresh(directory)
            data_path = Path(directory) / "results/player_intelligence/2026-27_player_game_v1.csv"
            data_path.parent.mkdir(parents=True)
            self.games.to_csv(data_path, index=False)
            before = data_path.read_bytes()
            self.discovery.side_effect = TimeoutError("NBA timed out")
            status = self.refresh(directory)
            self.assertEqual(data_path.read_bytes(), before)
        self.assertEqual(self.teams.call_count, 1)
        player = status["pipelines"]["players"]
        self.assertEqual(player["status"], "failed")
        self.assertIsNone(player["completedGames"])
        self.assertEqual(player["processedGames"], 2)
        self.assertEqual(player["lastSuccessfulCheckAt"], original["checkedAt"])

    def test_regressed_discovery_does_not_overwrite_existing_data(self):
        with tempfile.TemporaryDirectory() as directory:
            data_path = Path(directory) / "results/player_intelligence/2026-27_player_game_v1.csv"
            data_path.parent.mkdir(parents=True)
            self.games.to_csv(data_path, index=False)
            self.discovery.return_value = self.games.head(1)
            status = self.refresh(directory)
        self.teams.assert_not_called()
        self.players.assert_not_called()
        self.assertIn("omitted", status["sourceError"])


if __name__ == "__main__":
    unittest.main()
