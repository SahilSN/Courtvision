import tempfile
import fcntl
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from backfill_player_intelligence import backfill_season
from test_player_rating import make_appearance


class HistoricalPublisherTest(unittest.TestCase):
    def exercise_batch(self, directory, outcomes, failure_limit=3):
        rows = [pd.DataFrame([make_appearance(1, "Player", i, 0.3)]) for i in range(1, 5)]
        games = pd.concat(rows)[["gameId", "gameDate"]]
        cached_box = Path(directory) / "cache.pkl"
        cached_box.touch()
        with patch("backfill_player_intelligence.load_game_catalog", return_value=games), \
             patch("backfill_player_intelligence.load_training_games", return_value=games), \
             patch("backfill_player_intelligence.wpa_is_complete", return_value=True), \
             patch("backfill_player_intelligence.box_cache_path", return_value=cached_box), \
             patch("backfill_player_intelligence.load_cached_box_players"), \
             patch("backfill_player_intelligence.load_wpa_summary"), \
             patch("backfill_player_intelligence.fetch_and_cache_box_score"), \
             patch("backfill_player_intelligence.build_player_game_rows", side_effect=outcomes) as build:
            result = backfill_season("2025-26", output_dir=directory, failure_limit=failure_limit)
            return result, build.call_count

    def test_missing_possessions_are_refreshed_then_skipped_without_poisoning_checkpoint(self):
        rows = [pd.DataFrame([make_appearance(1, "Player", i, 0.3)]) for i in range(1, 5)]
        bad = rows[0].copy()
        bad["possessions"] = float("nan")
        with tempfile.TemporaryDirectory() as directory:
            failures, calls = self.exercise_batch(directory, [bad, bad, *rows[1:]])
            self.assertEqual(len(failures), 1)
            self.assertEqual(calls, 5)
            saved = pd.read_csv(Path(directory) / "2025-26_player_game_v1.csv")
            self.assertEqual(len(saved), 3)
            self.assertFalse(saved.possessions.isna().any())

    def test_circuit_stops_after_consecutive_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            failures, calls = self.exercise_batch(directory, [RuntimeError("NBA timed out")] * 4)
            self.assertEqual(calls, 3)
            self.assertEqual(len(failures), 3)

    def test_interruption_checkpoints_success_before_tenth_game(self):
        row = pd.DataFrame([make_appearance(1, "Player", 1, 0.3)])
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(KeyboardInterrupt):
                self.exercise_batch(directory, [row, KeyboardInterrupt()])
            saved = pd.read_csv(Path(directory) / "2025-26_player_game_v1.csv")
            self.assertEqual(len(saved), 1)
            self.assertTrue((Path(directory) / "2025-26_player_ratings_v1.csv").exists())

    def test_checkpoint_writer_lock_rejects_overlap(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / ".runtime"
            runtime.mkdir()
            with (runtime / "checkpoint.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaises(BlockingIOError):
                    backfill_season("2025-26", output_dir=directory)

    def test_checkpointed_games_are_skipped_on_resume(self):
        rows = pd.DataFrame([make_appearance(1, "Player", 1, 0.3)])
        games = rows[["gameId", "gameDate"]]
        with tempfile.TemporaryDirectory() as directory:
            cached_box = Path(directory) / "cache.pkl"
            cached_box.touch()
            with patch("backfill_player_intelligence.load_game_catalog", return_value=games), \
                 patch("backfill_player_intelligence.load_training_games", return_value=games), \
                 patch("backfill_player_intelligence.wpa_is_complete", return_value=True), \
                 patch("backfill_player_intelligence.box_cache_path", return_value=cached_box), \
                 patch("backfill_player_intelligence.load_cached_box_players"), \
                 patch("backfill_player_intelligence.load_wpa_summary"), \
                 patch("backfill_player_intelligence.build_player_game_rows", return_value=rows) as join, \
                 patch("backfill_player_intelligence.fetch_and_cache_box_score") as fetch:
                backfill_season("2025-26", cached_only=True, output_dir=directory)
                backfill_season("2025-26", cached_only=True, output_dir=directory)
                self.assertEqual(join.call_count, 1)
                fetch.assert_not_called()
            published = pd.read_csv(Path(directory) / "2025-26_player_game_v1.csv")
            self.assertEqual(len(published), 1)

    def test_incomplete_training_coverage_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch("backfill_player_intelligence.load_game_catalog", return_value=pd.DataFrame({"gameId": ["1", "2"]})), \
             patch("backfill_player_intelligence.load_training_games", return_value=pd.DataFrame({"gameId": ["1"]})):
            with self.assertRaisesRegex(ValueError, "coverage"):
                backfill_season("2025-26", output_dir=directory)


if __name__ == "__main__":
    unittest.main()
