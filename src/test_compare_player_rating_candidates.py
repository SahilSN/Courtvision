import unittest

import pandas as pd

from compare_player_rating_candidates import (
    build_candidate_diagnostics,
    build_candidate_table,
)


def make_row(
    person_id,
    player_name,
    game_id,
    game_date,
    minutes,
    possessions,
    net_wpa,
):
    return {
        "season": "2025-26",
        "gameDate": game_date,
        "gameId": game_id,
        "personId": person_id,
        "playerName": player_name,
        "teamTricode": "AAA",
        "opponentTricode": "BBB",
        "isHome": 1,
        "teamWin": 1,
        "starter": True,
        "minutes": minutes,
        "possessions": possessions,
        "attributedEvents": 1,
        "netWPA": net_wpa,
        "positiveWPA": max(net_wpa, 0.0),
        "negativeWPA": min(net_wpa, 0.0),
        "absoluteWPA": abs(net_wpa),
        "maxPositiveEvent": max(net_wpa, 0.0),
        "maxNegativeEvent": min(net_wpa, 0.0),
    }


class PlayerRatingCandidateComparisonTest(unittest.TestCase):
    def setUp(self):
        self.dataset = pd.DataFrame(
            [
                make_row(
                    1,
                    "One Game Star",
                    "0022500001",
                    "2025-10-21",
                    10.0,
                    20.0,
                    0.5,
                ),
                make_row(
                    2,
                    "Steady Player",
                    "0022500001",
                    "2025-10-21",
                    30.0,
                    60.0,
                    0.3,
                ),
                make_row(
                    2,
                    "Steady Player",
                    "0022500002",
                    "2025-10-23",
                    30.0,
                    60.0,
                    0.3,
                ),
                make_row(
                    3,
                    "Quiet Player",
                    "0022500002",
                    "2025-10-23",
                    30.0,
                    60.0,
                    0.0,
                ),
            ]
        )

    def test_shrinkage_reduces_small_sample_extreme(self):
        players = build_candidate_table(
            self.dataset,
            prior_games=5.0,
        ).set_index("personId")

        one_game = players.loc[1]
        steady = players.loc[2]

        self.assertLess(
            one_game["shrunkNetWPAper36"],
            one_game["netWPAper36"],
        )
        self.assertLess(
            one_game["minuteReliability"],
            steady["minuteReliability"],
        )
        self.assertEqual(int(steady["games"]), 2)

    def test_candidate_build_is_deterministic(self):
        first = build_candidate_table(self.dataset)
        second = build_candidate_table(
            self.dataset.sample(
                frac=1.0,
                random_state=42,
            )
        )

        pd.testing.assert_frame_equal(
            first,
            second,
        )

    def test_diagnostics_include_every_candidate(self):
        players = build_candidate_table(self.dataset)
        diagnostics = build_candidate_diagnostics(
            players,
            top_n=2,
        )

        self.assertEqual(len(diagnostics), 5)
        self.assertTrue(
            diagnostics["topNPlayersWithOneGame"].ge(0).all()
        )

    def test_prior_must_be_positive(self):
        with self.assertRaisesRegex(
            ValueError,
            "prior_games must be positive",
        ):
            build_candidate_table(
                self.dataset,
                prior_games=0,
            )

    def test_positive_possessions_are_required(self):
        dataset = self.dataset.copy()
        dataset["possessions"] = 0.0

        with self.assertRaisesRegex(
            ValueError,
            "requires positive possessions",
        ):
            build_candidate_table(dataset)


if __name__ == "__main__":
    unittest.main()
