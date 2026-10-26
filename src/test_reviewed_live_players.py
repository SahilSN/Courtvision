import unittest
from reviewed_live_players import candidates


class ReviewedPlayersTest(unittest.TestCase):
    def test_current_rookies_official_profile_identity_and_scope(self):
        for name, person, team in [('Christian Anderson',1643515,1610612766),('Meleek Thomas',1643509,1610612739)]:
            self.assertEqual(candidates(name,'2026-27',team),{person})
            self.assertNotIn(person,candidates(name,'2025-26',team))
            self.assertNotIn(person,candidates(name,'2026-27',1610612745))
        self.assertFalse(candidates('C Anderson','2026-27',1610612766))

    def test_reviewed_exact_season_team_scope(self):
        self.assertEqual(candidates('Darryn Peterson','2026-27',1610612762),{1643408})
        self.assertNotIn(1643408,candidates('Darryn Peterson','2025-26',1610612762))
        self.assertNotIn(1643408,candidates('Darryn Peterson','2026-27',1610612751))
        self.assertFalse(candidates('D Peterson','2026-27',1610612762))
