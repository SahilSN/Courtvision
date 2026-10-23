import unittest

import pandas as pd

from compare_player_rating_candidates import (
    build_candidate_diagnostics,
    build_candidate_table,
    build_chronological_holdout_diagnostics,
    build_walk_forward_diagnostics,
    summarize_walk_forward_diagnostics,
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

        self.assertEqual(len(diagnostics), 6)
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

    def test_holdout_uses_only_later_games(self):
        rows = []

        for game_number in range(1, 9):
            for person_id, name, wpa in (
                (1, "Consistent", 0.30),
                (2, "Quiet", 0.05),
            ):
                rows.append(
                    make_row(
                        person_id,
                        name,
                        f"00225000{game_number:02d}",
                        f"2025-10-{20 + game_number:02d}",
                        30.0,
                        60.0,
                        wpa,
                    )
                )

        diagnostics = build_chronological_holdout_diagnostics(
            pd.DataFrame(rows),
            holdout_fraction=0.25,
            min_training_games=2,
        )

        self.assertEqual(diagnostics.attrs["trainingGames"], 6)
        self.assertEqual(diagnostics.attrs["holdoutGames"], 2)
        self.assertEqual(diagnostics.attrs["cutoffDate"], "2025-10-27")
        self.assertEqual(diagnostics.attrs["eligiblePlayers"], 2)
        for correlation in diagnostics[
            "futureRankCorrelation"
        ]:
            self.assertAlmostEqual(correlation, 1.0)

    def test_holdout_arguments_are_validated(self):
        with self.assertRaisesRegex(
            ValueError,
            "holdout_fraction must be between",
        ):
            build_chronological_holdout_diagnostics(
                self.dataset,
                holdout_fraction=1.0,
            )

        with self.assertRaisesRegex(
            ValueError,
            "min_training_games must be positive",
        ):
            build_chronological_holdout_diagnostics(
                self.dataset,
                min_training_games=0,
            )

    def test_walk_forward_uses_expanding_training_windows(self):
        rows = []

        for game_number in range(1, 11):
            for person_id, name, wpa in (
                (1, "Consistent", 0.30),
                (2, "Quiet", 0.05),
            ):
                rows.append(
                    make_row(
                        person_id,
                        name,
                        f"00225000{game_number:02d}",
                        f"2025-11-{game_number:02d}",
                        30.0,
                        60.0,
                        wpa,
                    )
                )

        diagnostics = build_walk_forward_diagnostics(
            pd.DataFrame(rows),
            folds=3,
            initial_training_fraction=0.40,
            min_training_games=2,
        )
        summary = summarize_walk_forward_diagnostics(
            diagnostics
        )

        self.assertEqual(
            diagnostics["trainingGames"].drop_duplicates().tolist(),
            [4, 6, 8],
        )
        self.assertTrue(diagnostics["holdoutGames"].eq(2).all())
        self.assertEqual(len(diagnostics), 18)
        self.assertTrue(summary["validLiftFolds"].eq(3).all())
        self.assertTrue(summary["positiveLiftFolds"].eq(3).all())


if __name__ == "__main__":
    unittest.main()
