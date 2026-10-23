import tempfile
import unittest
from pathlib import Path

import pandas as pd

from player_career import build_player_career, load_published_player_data, season_coverage
from player_rating import build_player_ratings
from test_player_rating import make_appearance


class PlayerCareerTest(unittest.TestCase):
    def setUp(self):
        first = make_appearance(1, "Same Player", 1, 0.5)
        second = make_appearance(1, "Same Player", 2, -0.2)
        second.update(season="2026-27", gameId="0022600001", gameDate="2026-10-20",
                      teamTricode="CCC", minutes=10.0)
        self.games = pd.DataFrame([first, second, make_appearance(2, "Other", 1, 99.0)])

    def test_career_uses_identity_and_pools_appearances_not_season_means(self):
        career = build_player_career(self.games, 1)
        self.assertEqual(career["games"], 2)
        self.assertEqual(career["seasons"], 2)
        self.assertAlmostEqual(career["minutes"], 40.0)
        self.assertAlmostEqual(career["seasonNetWPA"], 0.3)
        pooled = self.games.loc[self.games["personId"].eq(1)].copy()
        pooled["season"] = "2025-26"
        expected = build_player_ratings(pooled).iloc[0]
        self.assertEqual(career["coveredRating"], expected["courtvisionRating"])

    def test_duplicates_and_absent_players_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            build_player_career(pd.concat([self.games, self.games.iloc[[0]]]), 1)
        with self.assertRaisesRegex(ValueError, "No covered"):
            build_player_career(self.games, 999)

    def test_coverage_requires_all_catalog_games_not_just_equal_counts(self):
        games = self.games.loc[self.games["season"].eq("2025-26")]
        catalog = pd.DataFrame({"gameId": ["0022500001", "0022500002"]})
        self.assertEqual(season_coverage("2025-26", games, catalog)["coverageStatus"], "Partial")
        self.assertEqual(season_coverage("2025-26", games, catalog.head(1))["coverageStatus"], "Complete")
        wrong = pd.DataFrame({"gameId": ["0022500999"]})
        with self.assertRaisesRegex(ValueError, "outside"):
            season_coverage("2025-26", games, wrong)
        self.assertEqual(season_coverage("2025-26", games)["coverageStatus"], "Unknown")
        current = self.games.loc[self.games["season"].eq("2026-27")]
        self.assertEqual(season_coverage("2026-27", current)["coverageStatus"], "In progress")

    def test_published_loader_requires_pairs_and_checks_season(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            games = self.games.loc[self.games["season"].eq("2025-26")]
            ratings = build_player_ratings(games)
            path = root / "2025-26_player_ratings_v1.csv"
            ratings.to_csv(path, index=False)
            self.assertTrue(load_published_player_data(root)[0].empty)
            games.to_csv(root / "2025-26_player_game_v1.csv", index=False)
            summaries, appearances, coverage = load_published_player_data(root)
            self.assertEqual(len(summaries), 2)
            self.assertEqual(len(appearances), 2)
            self.assertEqual(coverage.iloc[0]["coverageStatus"], "Unknown")
            ratings["season"] = "2024-25"
            ratings.to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, "does not match"):
                load_published_player_data(root)


if __name__ == "__main__":
    unittest.main()
