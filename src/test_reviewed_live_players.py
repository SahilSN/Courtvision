import unittest
import reviewed_live_players
from reviewed_live_players import candidates


class ReviewedPlayersTest(unittest.TestCase):
    def test_late_warriors_participants_are_exact_and_scoped(self):
        for name, person in [('Graham Ike',1643633), ('LJ Cryer',1643018)]:
            self.assertEqual(candidates(name,'2026-27',1610612744),{person})
            for season, team in [('2025-26',1610612744), ('2026-27',1610612743)]:
                self.assertEqual(candidates(name,season,team),
                                 reviewed_live_players._static_index().get(
                                     reviewed_live_players.normalize_name(name),set()))
        self.assertFalse(candidates('G Ike','2026-27',1610612744))

    def test_late_bench_participants_exact_scope(self):
        for name, person, team in [('Zuby Ejiofor',1643544,1610612737),
                                   ('Bruce Thornton',1643570,1610612745)]:
            self.assertEqual(candidates(name,'2026-27',team),{person})
            self.assertNotIn(person,candidates(name,'2025-26',team))
            self.assertNotIn(person,candidates(name,'2026-27',1610612738))
        self.assertFalse(candidates('B Thornton','2026-27',1610612745))

    def test_western_games_exact_official_identities(self):
        for name, person, team in [('Kingston Flemings',1643412,1610612737),
                ('Cameron Boozer',1643409,1610612763),('Yaxel Lendeborg',1642865,1610612744),
                ('Bryce Hopkins',1643624,1610612743),('Trevon Brazile',1642350,1610612743)]:
            self.assertEqual(candidates(name,'2026-27',team),{person})
            self.assertNotIn(person,candidates(name,'2025-26',team))
            self.assertNotIn(person,candidates(name,'2026-27',1610612745))

    def test_reviewed_team_disambiguates_retired_namesake_only_in_scope(self):
        from unittest.mock import patch
        import reviewed_live_players
        self.assertEqual(candidates('Brandon Williams','2026-27',1610612744),{1630314})
        self.assertEqual(candidates('Brandon Williams','2025-26',1610612744),{1585,1630314})
        self.assertEqual(candidates('Brandon Williams','2026-27',1610612745),{1585,1630314})
        with patch.object(reviewed_live_players,'REVIEWED',reviewed_live_players.REVIEWED +
                (('2026-27',1610612744,'Brandon Williams',1585,'conflicting-test-source'),)):
            self.assertEqual(candidates('Brandon Williams','2026-27',1610612744),{1585,1630314})

    def test_late_participating_boston_rookie(self):
        self.assertEqual(candidates('Chris Cenac Jr.','2026-27',1610612738),{1643416})
        self.assertNotIn(1643416,candidates('Chris Cenac Jr.','2025-26',1610612738))
        self.assertNotIn(1643416,candidates('Chris Cenac Jr.','2026-27',1610612741))
        self.assertFalse(candidates('C Cenac','2026-27',1610612738))

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
