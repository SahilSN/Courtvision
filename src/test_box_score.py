import unittest

import pandas as pd

from box_score import (
    deduplicate_advanced_players,
    merge_player_stats,
)


MERGE_KEYS = [
    "gameId",
    "teamId",
    "personId",
]


class BoxScoreMergeTest(unittest.TestCase):
    def test_blank_historical_duplicate_prefers_played_row(self):
        traditional = pd.DataFrame(
            [
                {
                    "gameId": "0022400103",
                    "teamId": 1610612764,
                    "personId": 202685,
                    "firstName": "Jonas",
                    "familyName": "Valančiūnas",
                    "nameI": "J. Valančiūnas",
                    "minutes": "22:15",
                    "position": "C",
                }
            ]
        )
        advanced = pd.DataFrame(
            [
                {
                    "gameId": "0022400103",
                    "teamId": 1610612764,
                    "personId": 202685,
                    "firstName": "Jonas",
                    "familyName": "Valanciunas",
                    "minutes": "",
                    "possessions": None,
                },
                {
                    "gameId": "0022400103",
                    "teamId": 1610612764,
                    "personId": 202685,
                    "firstName": "Jonas",
                    "familyName": "Valančiūnas",
                    "minutes": "22:15",
                    "possessions": 45,
                },
            ]
        )

        merged = merge_player_stats(
            traditional,
            advanced,
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual(float(merged.iloc[0]["possessions"]), 45.0)
        self.assertEqual(merged.iloc[0]["fullName"], "Jonas Valančiūnas")

    def test_unique_advanced_rows_are_preserved(self):
        advanced = pd.DataFrame(
            [
                {
                    "gameId": "0022400001",
                    "teamId": 1,
                    "personId": 10,
                    "minutes": "20:00",
                    "possessions": 40,
                },
                {
                    "gameId": "0022400001",
                    "teamId": 1,
                    "personId": 11,
                    "minutes": "10:00",
                    "possessions": 20,
                },
            ]
        )

        result = deduplicate_advanced_players(
            advanced,
            MERGE_KEYS,
        )

        pd.testing.assert_frame_equal(result, advanced)

    def test_ambiguous_duplicates_fail_loudly(self):
        advanced = pd.DataFrame(
            [
                {
                    "gameId": "0022400001",
                    "teamId": 1,
                    "personId": 10,
                    "minutes": "20:00",
                    "possessions": 40,
                },
                {
                    "gameId": "0022400001",
                    "teamId": 1,
                    "personId": 10,
                    "minutes": "21:00",
                    "possessions": 42,
                },
            ]
        )

        with self.assertRaisesRegex(
            ValueError,
            "Ambiguous duplicate advanced player rows",
        ):
            deduplicate_advanced_players(
                advanced,
                MERGE_KEYS,
            )


if __name__ == "__main__":
    unittest.main()
