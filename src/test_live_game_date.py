from datetime import datetime
import unittest
from zoneinfo import ZoneInfo

from live_game_date import eligible_game_date


class GameDateTest(unittest.TestCase):
    def test_midnight_and_cutoff(self):
        for instant, accepted in [('2026-10-26T23:59:59', True),
                                  ('2026-10-27T00:00:00', True),
                                  ('2026-10-27T05:59:59', True),
                                  ('2026-10-27T06:00:00', False)]:
            now = datetime.fromisoformat(instant).replace(tzinfo=ZoneInfo('America/New_York'))
            with self.subTest(instant=instant):
                self.assertEqual(eligible_game_date('2026-10-26', now), accepted)
                self.assertFalse(eligible_game_date('2026-10-25', now))
                self.assertFalse(eligible_game_date('2026-10-28', now))

    def test_dst_and_year_boundary(self):
        for instant, day in [('2026-03-08T03:30:00-04:00', '2026-03-07'),
                             ('2026-11-01T01:30:00-04:00', '2026-10-31'),
                             ('2026-11-01T01:30:00-05:00', '2026-10-31'),
                             ('2027-01-01T00:15:00-05:00', '2026-12-31')]:
            self.assertTrue(eligible_game_date(day, datetime.fromisoformat(instant)))

    def test_bad_dates_and_naive_clock_fail_closed(self):
        now = datetime.fromisoformat('2026-10-27T00:15:00-04:00')
        for day in (None, '', '20261026', '2026-02-30', '2026-10-28'):
            self.assertFalse(eligible_game_date(day, now))
        self.assertFalse(eligible_game_date('2026-10-26', now.replace(tzinfo=None)))
