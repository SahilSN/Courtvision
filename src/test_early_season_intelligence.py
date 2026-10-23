import unittest

import pandas as pd

from team_season_intelligence import (
    INITIAL_RATING,
    build_team_summary,
)
from update_live_season import (
    include_idle_teams_in_ratings,
)


class EarlySeasonIntelligenceTest(unittest.TestCase):
    def test_idle_teams_are_added_at_neutral_rating(self):
        ratings = pd.DataFrame(
            [
                {
                    "ratingRank": 1,
                    "team": "ATL",
                    "wins": 1,
                    "losses": 0,
                    "currentRating": 1510.0,
                    "peakRating": 1510.0,
                    "lowestRating": 1500.0,
                }
            ]
        )

        complete = include_idle_teams_in_ratings(
            ratings
        )

        self.assertEqual(
            len(complete),
            30,
        )

        cleveland = complete.loc[
            complete["team"] == "CLE"
        ].iloc[0]

        self.assertEqual(
            int(cleveland["wins"]),
            0,
        )
        self.assertEqual(
            int(cleveland["losses"]),
            0,
        )
        self.assertEqual(
            float(cleveland["currentRating"]),
            INITIAL_RATING,
        )

    def test_summary_includes_teams_without_games(self):
        ratings = include_idle_teams_in_ratings(
            pd.DataFrame(
                [
                    {
                        "ratingRank": 1,
                        "team": "ATL",
                        "wins": 1,
                        "losses": 0,
                        "currentRating": 1510.0,
                        "peakRating": 1510.0,
                        "lowestRating": 1500.0,
                    }
                ]
            )
        )

        team_history = pd.DataFrame(
            [
                {
                    "team": "ATL",
                    "teamGameNumber": 1,
                    "teamWin": 1,
                    "ratingChange": 10.0,
                    "gameDate": "2026-10-20",
                }
            ]
        )

        summary = build_team_summary(
            team_history,
            ratings,
        )

        cleveland = summary.loc[
            summary["team"] == "CLE"
        ].iloc[0]

        self.assertEqual(
            len(summary),
            30,
        )
        self.assertEqual(
            int(cleveland["gamesPlayed"]),
            0,
        )
        self.assertTrue(
            pd.isna(cleveland["lastGameDate"])
        )


if __name__ == "__main__":
    unittest.main()
