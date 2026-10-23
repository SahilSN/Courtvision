import unittest

from live_analysis import (
    apply_current_season_pregame_smoothing,
    smoothed_pregame_win_pct,
)
from season_config import (
    CURRENT_SEASON,
    CURRENT_SEASON_TYPE,
)


class LivePregameSmoothingTest(unittest.TestCase):
    def test_neutral_prior_stabilizes_early_records(self):
        self.assertAlmostEqual(
            smoothed_pregame_win_pct(0, 0),
            0.5,
        )
        self.assertAlmostEqual(
            smoothed_pregame_win_pct(1, 0),
            2.0 / 3.0,
        )
        self.assertAlmostEqual(
            smoothed_pregame_win_pct(0, 1),
            1.0 / 3.0,
        )

    def test_current_regular_season_uses_smoothed_model_inputs(self):
        context = {
            "homePreGameWins": 1,
            "homePreGameLosses": 0,
            "awayPreGameWins": 0,
            "awayPreGameLosses": 0,
            "homePreGameWinPct": 1.0,
            "awayPreGameWinPct": 0.5,
            "strengthDifference": 0.5,
        }

        result = apply_current_season_pregame_smoothing(
            context=context,
            season=CURRENT_SEASON,
            season_type=CURRENT_SEASON_TYPE,
        )

        self.assertEqual(
            result["homePreGameWins"],
            1,
        )
        self.assertEqual(
            result["homePreGameLosses"],
            0,
        )
        self.assertAlmostEqual(
            result["homePreGameWinPct"],
            2.0 / 3.0,
        )
        self.assertAlmostEqual(
            result["awayPreGameWinPct"],
            0.5,
        )
        self.assertAlmostEqual(
            result["strengthDifference"],
            1.0 / 6.0,
        )

    def test_historical_context_is_unchanged(self):
        context = {
            "homePreGameWins": 1,
            "homePreGameLosses": 0,
            "awayPreGameWins": 0,
            "awayPreGameLosses": 0,
            "homePreGameWinPct": 1.0,
            "awayPreGameWinPct": 0.5,
            "strengthDifference": 0.5,
        }

        result = apply_current_season_pregame_smoothing(
            context=context,
            season="2025-26",
            season_type="Regular Season",
        )

        self.assertIs(
            result,
            context,
        )


if __name__ == "__main__":
    unittest.main()
