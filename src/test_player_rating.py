import unittest

import pandas as pd

from player_rating import (
    build_player_ratings,
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


if __name__ == "__main__":
    unittest.main()
