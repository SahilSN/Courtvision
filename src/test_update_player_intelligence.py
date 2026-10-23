import tempfile
import unittest
from pathlib import Path

import pandas as pd

from player_rating_dataset import OUTPUT_COLUMNS
from update_player_intelligence import (
    update_player_intelligence,
)


def completed_games():
    return pd.DataFrame(
        [
            {
                "season": "2026-27",
                "gameDate": "2026-10-20",
                "gameId": "0022600001",
                "homeTeam": "AAA",
                "awayTeam": "BBB",
                "homeWin": 1,
            },
            {
                "season": "2026-27",
                "gameDate": "2026-10-21",
                "gameId": "0022600002",
                "homeTeam": "AAA",
                "awayTeam": "BBB",
                "homeWin": 0,
            },
        ]
    )


def player_rows(season, game):
    row = {
        "season": season,
        "gameDate": game.gameDate,
        "gameId": game.gameId,
        "personId": 1,
        "playerName": "Test Player",
        "teamTricode": "AAA",
        "opponentTricode": "BBB",
        "isHome": 1,
        "teamWin": int(game.homeWin),
        "starter": True,
        "minutes": 30.0,
        "possessions": 60.0,
        "attributedEvents": 2,
        "netWPA": 0.25,
        "positiveWPA": 0.25,
        "negativeWPA": 0.0,
        "absoluteWPA": 0.25,
        "maxPositiveEvent": 0.15,
        "maxNegativeEvent": 0.0,
    }

    return pd.DataFrame(
        [row],
        columns=OUTPUT_COLUMNS,
    )


class UpdatePlayerIntelligenceTest(unittest.TestCase):
    def test_no_completed_games_is_a_valid_empty_state(self):
        with tempfile.TemporaryDirectory() as output_dir:
            result = update_player_intelligence(
                output_dir=output_dir,
                completed_games=pd.DataFrame(),
            )
        self.assertTrue(result["dataset"].empty)
        self.assertEqual(result["failures"], [])

    def test_invalid_game_rows_do_not_block_other_games(self):
        def processor(season, _season_type, game):
            rows = player_rows(season, game)
            if game.gameId == "0022600001":
                rows["gameId"] = "0022600999"
            return rows

        with tempfile.TemporaryDirectory() as output_dir:
            result = update_player_intelligence(
                output_dir=output_dir,
                completed_games=completed_games(),
                game_processor=processor,
            )
        self.assertEqual(len(result["failures"]), 1)
        self.assertEqual(result["dataset"]["gameId"].tolist(), ["0022600002"])

    def test_incremental_update_skips_published_games(self):
        calls = []

        def processor(season, _season_type, game):
            calls.append(game.gameId)
            return player_rows(season, game)

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory)
            first = update_player_intelligence(
                season="2026-27",
                output_dir=output_dir,
                completed_games=completed_games(),
                max_new_games=1,
                game_processor=processor,
            )
            second = update_player_intelligence(
                season="2026-27",
                output_dir=output_dir,
                completed_games=completed_games(),
                game_processor=processor,
            )
            third = update_player_intelligence(
                season="2026-27",
                output_dir=output_dir,
                completed_games=completed_games(),
                game_processor=processor,
            )

            self.assertEqual(first["dataset"]["gameId"].nunique(), 1)
            self.assertEqual(second["dataset"]["gameId"].nunique(), 2)
            self.assertEqual(third["dataset"]["gameId"].nunique(), 2)
            self.assertEqual(calls, ["0022600001", "0022600002"])
            self.assertTrue(
                (
                    output_dir
                    / "2026-27_player_ratings_v1.csv"
                ).exists()
            )

    def test_failures_remain_pending_for_next_run(self):
        attempts = []

        def processor(_season, _season_type, game):
            attempts.append(game.gameId)
            raise RuntimeError("temporary source failure")

        with tempfile.TemporaryDirectory() as temporary_directory:
            result = update_player_intelligence(
                season="2026-27",
                output_dir=temporary_directory,
                completed_games=completed_games().head(1),
                game_processor=processor,
            )

        self.assertEqual(attempts, ["0022600001"])
        self.assertEqual(len(result["failures"]), 1)
        self.assertTrue(result["dataset"].empty)


if __name__ == "__main__":
    unittest.main()
