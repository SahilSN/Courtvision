import unittest

import pandas as pd

from player_rating_dataset import (
    build_player_game_rows,
    parse_minutes,
    validate_player_game_dataset,
)


class PlayerRatingDatasetTest(unittest.TestCase):
    def test_parse_minutes(self):
        self.assertAlmostEqual(parse_minutes("12:30"), 12.5)
        self.assertAlmostEqual(parse_minutes("PT7M15.00S"), 7.25)
        self.assertEqual(parse_minutes(""), 0.0)

    def test_zero_event_participant_is_preserved(self):
        team_games = pd.DataFrame(
            [
                {
                    "season": "2025-26",
                    "gameId": "0022500001",
                    "gameDate": "2025-10-21",
                    "teamTricode": "CLE",
                    "opponentTricode": "PHI",
                    "isHome": 0,
                    "teamWin": 1,
                },
                {
                    "season": "2025-26",
                    "gameId": "0022500001",
                    "gameDate": "2025-10-21",
                    "teamTricode": "PHI",
                    "opponentTricode": "CLE",
                    "isHome": 1,
                    "teamWin": 0,
                },
            ]
        )
        box_players = pd.DataFrame(
            [
                {
                    "personId": 1,
                    "fullName": "Impact Player",
                    "teamTricode": "CLE",
                    "minutes": "30:00",
                    "starter": True,
                    "possessions": 60.0,
                },
                {
                    "personId": 2,
                    "fullName": "Quiet Player",
                    "teamTricode": "CLE",
                    "minutes": "05:00",
                    "starter": False,
                    "possessions": 10.0,
                },
            ]
        )
        wpa_summary = pd.DataFrame(
            [
                {
                    "personId": 1,
                    "teamTricode": "CLE",
                    "events": 4,
                    "netWPA": 0.1,
                    "positiveWPA": 0.12,
                    "negativeWPA": -0.02,
                    "absoluteWPA": 0.14,
                    "maxPositiveEvent": 0.05,
                    "maxNegativeEvent": -0.02,
                }
            ]
        )

        result = build_player_game_rows(
            season="2025-26",
            game_id="0022500001",
            team_games=team_games,
            box_players=box_players,
            wpa_summary=wpa_summary,
        )

        validate_player_game_dataset(result)
        quiet = result.loc[result["personId"] == 2].iloc[0]
        self.assertEqual(int(quiet["attributedEvents"]), 0)
        self.assertEqual(float(quiet["netWPA"]), 0.0)
        self.assertEqual(float(quiet["minutes"]), 5.0)
        self.assertAlmostEqual(
            float(result["netWPA"].sum()),
            float(wpa_summary["netWPA"].sum()),
        )


if __name__ == "__main__":
    unittest.main()
