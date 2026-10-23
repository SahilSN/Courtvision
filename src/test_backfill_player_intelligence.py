import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from backfill_player_intelligence import backfill_season
from test_player_rating import make_appearance


class HistoricalPublisherTest(unittest.TestCase):
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
        with patch("backfill_player_intelligence.load_game_catalog", return_value=pd.DataFrame({"gameId": ["1", "2"]})), \
             patch("backfill_player_intelligence.load_training_games", return_value=pd.DataFrame({"gameId": ["1"]})):
            with self.assertRaisesRegex(ValueError, "coverage"):
                backfill_season("2025-26")


if __name__ == "__main__":
    unittest.main()
