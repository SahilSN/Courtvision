from datetime import datetime
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from streamlit.testing.v1 import AppTest


class InactiveBetaViewTest(unittest.TestCase):
    def test_fragment_gate_blocks_requests_and_model(self):
        root=Path(__file__).resolve().parents[1]
        day=json.loads((root/'results/live_context/2026-27_day_context_v1.json').read_text())
        instant=datetime.fromisoformat(day['gameDate']).replace(tzinfo=ZoneInfo('America/New_York'))
        game=day['games'][0]['gameId']
        script=f"from live_beta_view import render_live_beta\nrender_live_beta({str(root)!r},[{game!r}],rollout_guard=lambda:())"
        with patch('live_beta_view.datetime') as clock, patch('live_beta_view.scoreboard_event') as fetch, patch('live_beta_view.cpu_artifacts') as model:
            clock.now.return_value=instant
            app=AppTest.from_string(script,default_timeout=60).run()
            self.assertFalse(app.exception)
            self.assertIn('paused',' '.join(x.value for x in app.info))
            fetch.assert_not_called();model.assert_not_called()

    def test_scheduled_view_has_no_model_or_estimate_and_refresh_defaults_off(self):
        root=Path(__file__).resolve().parents[1]
        day=json.loads((root/'results/live_context/2026-27_day_context_v1.json').read_text())
        instant=datetime.fromisoformat(day['gameDate']).replace(tzinfo=ZoneInfo('America/New_York'))
        game=day['games'][0]['gameId']
        script=f"from live_beta_view import render_live_beta\nrender_live_beta({str(root)!r},[{game!r}])"
        with patch('live_beta_view.datetime') as clock, \
             patch('live_beta_view.scoreboard_event',return_value={'competitions':[{'status':{'type':{'state':'pre'}}}]}), \
             patch('live_beta_view.cpu_artifacts') as model:
            clock.now.return_value=instant
            app=AppTest.from_string(script,default_timeout=60).run()
            self.assertFalse(app.exception)
            self.assertFalse(app.toggle[0].value)
            self.assertIn('has not started',' '.join(x.value for x in app.info))
            self.assertFalse(app.dataframe)
            model.assert_not_called()
