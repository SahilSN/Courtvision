import unittest
from reviewed_live_players import candidates


class ReviewedPlayersTest(unittest.TestCase):
    def test_expansion_rookies_exact_scope(self):
        for name,person,team in [('Caleb Wilson',1643410,1610612741),('Tobe Awaka',1643591,1610612741),
                ('Dailyn Swain',1643517,1610612741),('Jaylin Sellers',1643637,1610612741),
                ('Morez Johnson Jr.',1643516,1610612742),('Sergio de Larrea',1643547,1610612742),
                ('Nate Ament',1643417,1610612749),('Brayden Burries',1643415,1610612749)]:
            with self.subTest(name=name):
                self.assertEqual(candidates(name,'2026-27',team),{person})
                self.assertNotIn(person,candidates(name,'2025-26',team))
                self.assertNotIn(person,candidates(name,'2026-27',1610612745))
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
