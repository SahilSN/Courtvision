import unittest

import pandas as pd

from player_rating import (
    build_player_ratings,
    build_player_rating_history,
)


def make_appearance(
    person_id,
    player_name,
    game_number,
    net_wpa,
):
    return {
        "season": "2025-26",
        "gameDate": f"2025-11-{game_number:02d}",
        "gameId": f"00225000{game_number:02d}",
        "personId": person_id,
        "playerName": player_name,
        "teamTricode": "AAA",
        "opponentTricode": "BBB",
        "isHome": 1,
        "teamWin": 1,
        "starter": True,
        "minutes": 30.0,
        "possessions": 60.0,
        "attributedEvents": 1,
        "netWPA": net_wpa,
        "positiveWPA": max(net_wpa, 0.0),
        "negativeWPA": min(net_wpa, 0.0),
        "absoluteWPA": abs(net_wpa),
        "maxPositiveEvent": max(net_wpa, 0.0),
        "maxNegativeEvent": min(net_wpa, 0.0),
    }


class PlayerRatingTest(unittest.TestCase):
    def setUp(self):
        rows = []
        players = (
            (1, "Baseline", 10, 0.25),
            (2, "High Impact", 10, 0.50),
            (3, "Provisional", 3, 0.40),
            (4, "Limited", 2, 0.60),
        )

        for person_id, name, games, net_wpa in players:
            for game_number in range(1, games + 1):
                rows.append(
                    make_appearance(
                        person_id,
                        name,
                        game_number,
                        net_wpa,
                    )
                )

        self.dataset = pd.DataFrame(rows)

    def test_reference_performance_rates_to_100(self):
        ratings = build_player_ratings(
            self.dataset
        ).set_index("personId")

        self.assertAlmostEqual(
            ratings.loc[1, "courtvisionRating"],
            100.0,
        )
        self.assertGreater(
            ratings.loc[2, "courtvisionRating"],
            100.0,
        )

    def test_status_and_eligibility_are_honest(self):
        ratings = build_player_ratings(
            self.dataset
        ).set_index("personId")

        self.assertEqual(ratings.loc[1, "ratingStatus"], "Qualified")
        self.assertEqual(ratings.loc[3, "ratingStatus"], "Provisional")
        self.assertEqual(ratings.loc[4, "ratingStatus"], "Limited")
        self.assertTrue(bool(ratings.loc[3, "leaderboardEligible"]))
        self.assertFalse(bool(ratings.loc[4, "leaderboardEligible"]))
        self.assertTrue(pd.isna(ratings.loc[4, "courtvisionRank"]))

    def test_quality_and_season_value_rank_separately(self):
        ratings = build_player_ratings(
            self.dataset
        ).set_index("personId")

        self.assertEqual(int(ratings.loc[2, "courtvisionRank"]), 1)
        self.assertEqual(int(ratings.loc[2, "seasonValueRank"]), 1)
        self.assertGreater(
            ratings.loc[2, "seasonNetWPA"],
            ratings.loc[3, "seasonNetWPA"],
        )

    def test_multiple_seasons_are_rejected(self):
        dataset = self.dataset.copy()
        dataset.loc[dataset.index[0], "season"] = "2024-25"

        with self.assertRaisesRegex(
            ValueError,
            "exactly one season",
        ):
            build_player_ratings(dataset)

    def test_history_matches_every_prefix_of_frozen_rating(self):
        dataset = self.dataset.copy()
        dataset.loc[dataset["personId"].eq(2), "netWPA"] = [
            0.5, -0.3, 0.1, 0.9, -0.8, 0.3, 0.2, -0.1, 0.4, 0.7
        ]
        history = build_player_rating_history(dataset.sample(frac=1, random_state=4), 2)
        for row in history.itertuples():
            prefix = dataset.loc[pd.to_datetime(dataset["gameDate"]).le(row.gameDate)]
            expected = build_player_ratings(prefix).set_index("personId").loc[2]
            self.assertEqual(row.courtvisionRating, expected["courtvisionRating"])
            self.assertAlmostEqual(row.seasonNetWPA, expected["seasonNetWPA"])
            self.assertAlmostEqual(row.ratingReliability, expected["ratingReliability"])
            self.assertEqual(row.ratingStatus, expected["ratingStatus"])
        self.assertEqual(history["ratingStatus"].iloc[0], "Limited")
        self.assertEqual(history["ratingStatus"].iloc[2], "Provisional")
        self.assertEqual(history["ratingStatus"].iloc[-1], "Qualified")

    def test_history_preserves_team_changes_and_missing_player(self):
        dataset = self.dataset.copy()
        dataset.loc[dataset["gameDate"].ge("2025-11-05"), "teamTricode"] = "CCC"
        history = build_player_rating_history(dataset, 1)
        self.assertEqual(history["teamTricode"].iloc[0], "AAA")
        self.assertEqual(history["teamTricode"].iloc[-1], "CCC")
        self.assertEqual(history["games"].iloc[-1], 10)
        self.assertTrue(build_player_rating_history(dataset, 9999).empty)

    def test_history_rejects_duplicates_and_mixed_seasons(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            build_player_rating_history(
                pd.concat([self.dataset, self.dataset.iloc[[0]]]), 1
            )
        dataset = self.dataset.copy()
        dataset.loc[0, "season"] = "2024-25"
        with self.assertRaisesRegex(ValueError, "exactly one season"):
            build_player_rating_history(dataset, 1)


if __name__ == "__main__":
    unittest.main()
