import os
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from player_rating import build_player_ratings, build_player_rating_history
from test_player_rating import make_appearance


class PlayerRatingScopeTest(unittest.TestCase):
    def test_prior_career_cannot_advantage_identical_current_season_performance(self):
        veteran=make_appearance(1,'Veteran',1,0.2)
        rookie=make_appearance(2,'Rookie',1,0.2)
        for row in (veteran,rookie):
            row.update(season='2026-27',gameId='0022600001',gameDate='2026-10-20')
        old=make_appearance(1,'Veteran',1,99.0)
        all_games=pd.DataFrame([old,veteran,rookie])
        current=all_games.loc[all_games.season.eq('2026-27')]
        ratings=build_player_ratings(current).set_index('personId')
        self.assertEqual(ratings.loc[1,'courtvisionRating'],ratings.loc[2,'courtvisionRating'])
        history=build_player_rating_history(current,1)
        self.assertEqual(history.games.tolist(),[1])
        self.assertEqual(history.seasonNetWPA.tolist(),[0.2])
        self.assertEqual(history.courtvisionRating.iloc[-1],ratings.loc[1,'courtvisionRating'])
        with self.assertRaises(ValueError):build_player_ratings(all_games)
        with self.assertRaises(ValueError):build_player_rating_history(all_games,1)

    def test_published_season_default_and_optional_career_round_trip(self):
        root=Path(__file__).resolve().parents[1]
        with patch.dict(os.environ,{'COURTVISION_DEPLOYMENT_PROFILE':'published'}), \
             patch('requests.sessions.Session.request',side_effect=AssertionError('No network')):
            app=AppTest.from_file(str(root/'dashboard/app.py'),default_timeout=60).run()
            app.sidebar.radio(key='courtvision_season_intelligence_view').set_value('Players').run()
            self.assertFalse(app.exception)
            scope=app.radio(key='courtvision_player_rating_scope')
            self.assertEqual(scope.value,'Season · resets each year')
            self.assertEqual(scope.options[0],'Season · resets each year')
            app.radio(key='courtvision_player_rating_scope').set_value('Career · covered seasons').run()
            self.assertFalse(app.exception)
            self.assertEqual(app.sidebar.radio(key='courtvision_season_intelligence_view').value,'Player Career')
            self.assertTrue(app.sidebar.selectbox(key='courtvision_season_intelligence_season').disabled)
            app.radio(key='courtvision_player_rating_scope').set_value('Season · resets each year').run()
            self.assertFalse(app.exception)
            self.assertEqual(app.sidebar.radio(key='courtvision_season_intelligence_view').value,'Players')
            self.assertFalse(app.sidebar.selectbox(key='courtvision_season_intelligence_season').disabled)


if __name__=='__main__':unittest.main()
