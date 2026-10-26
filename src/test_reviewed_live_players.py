import unittest
from reviewed_live_players import candidates


class ReviewedPlayersTest(unittest.TestCase):
    def test_reviewed_exact_season_team_scope(self):
        self.assertEqual(candidates('Darryn Peterson','2026-27',1610612762),{1643408})
        self.assertNotIn(1643408,candidates('Darryn Peterson','2025-26',1610612762))
        self.assertNotIn(1643408,candidates('Darryn Peterson','2026-27',1610612751))
        self.assertFalse(candidates('D Peterson','2026-27',1610612762))
