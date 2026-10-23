import unittest

from replay_collection import load_collection
from replay_exploration import game_overview, replay_bookmarks


class ReplayExplorationTest(unittest.TestCase):
    def test_summary_and_exact_bookmarks_for_all_games(self):
        for game_id, (data, timeline) in load_collection().items():
            with self.subTest(game=game_id):
                summary = game_overview(data, timeline)
                self.assertIn("won by", summary)
                self.assertIn("not explanations", summary)
                periods, swings = replay_bookmarks(data, timeline)
                self.assertEqual(len(periods), int(timeline.period.max()))
                self.assertTrue(swings)
                for _, index in periods + swings:
                    self.assertIn(index, timeline.index)
                if game_id == "0022500001":
                    self.assertIn("OKC won by 1 point after 2 overtime periods", summary)

    def test_unmatched_or_ambiguous_turning_point_is_not_guessed(self):
        data, timeline = next(iter(load_collection().values()))
        data = {**data, "turningPoints": [{**data["turningPoints"][0], "Play": "not a real play"}]}
        self.assertEqual(replay_bookmarks(data, timeline)[1], [])
